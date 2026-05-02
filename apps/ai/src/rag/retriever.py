"""法令検索（RAG retriever）— クエリ → 埋め込み → pgvector → (任意で rerank)。

このファイルが扱う AI 概念：

* **Dense retrieval (semantic search)** — クエリを埋め込みベクトルに変換し、
  事前に格納してある条文ベクトルとの **cosine 距離** で近いものを引く。
  キーワード一致（BM25 等）ではなく意味的に近いものを拾えるのが強み。
* **pgvector の ``<=>`` 演算子** — cosine 距離（0 = 同方向, 2 = 反対）。
  類似度に直すなら ``1 - distance``。
  事前に HNSW (Hierarchical Navigable Small World) 索引を張っておけば、
  ``ORDER BY embedding <=> $1`` で近似最近傍探索が走る。
* **Voyage の input_type** — 同じ ``voyage-3`` でも、
  保存時は ``input_type="document"``、検索時は ``input_type="query"`` を渡す。
  両者は内部的に若干異なる空間に写像されており、対称検索より精度が出る。
* **2 段検索 (dense → rerank)** — dense は速いが top-1 精度が荒い。
  cross-encoder rerank（``rerank-2``）でクエリと候補を **同時に** 読ませて
  並べ替えると上位の精度が大きく改善する代わりに API 呼び出し 1 回ぶん遅い。
  ``settings.rerank_enabled`` でオプトイン。

呼び出し経路: ``agents/*`` から ``retrieve()`` を直接呼ぶ。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache

import voyageai

from ..config import settings
from ..observability import observe
from .db import get_pool


# frozen=True: 不変オブジェクトにすることで、エージェント間で共有しても安全。
# slots=True: __slots__ を生成して 1 件あたりのメモリ・属性アクセスを最適化
# （RAG では数十〜数百件単位で持つので地味に効く）。
@dataclass(frozen=True, slots=True)
class Citation:
    """1 件の引用候補。SQL の 1 行 + rerank 後のスコアに対応。"""

    law_id: str
    law_title: str
    law_num: str
    article_no: str | None
    article_title: str | None
    body: str
    source_url: str
    # cosine 類似度（dense 時）または rerank の relevance_score（rerank 時）。
    # rerank 時は意味が変わるため、値を絶対値で比較しないこと。
    score: float


@lru_cache(maxsize=1)
def _voyage() -> voyageai.AsyncClient:
    """Voyage の非同期クライアントをプロセス内シングルトン化して接続を再利用。"""
    return voyageai.AsyncClient(api_key=settings.voyage_api_key)


@observe(name="rag.embed_query")
async def _embed_query(query: str) -> list[float]:
    """検索クエリを埋め込みベクトル（``embedding_dim`` 次元）に変換する。

    ``input_type="query"`` がポイント。ingest 側は ``"document"`` で埋め込んで
    保存しているため、検索時はクエリ向けに最適化された埋め込みを使うことで
    対称型検索より精度が上がる（asymmetric retrieval と呼ぶ）。
    """
    res = await _voyage().embed(
        texts=[query],
        model=settings.embedding_model,
        input_type="query",
    )
    return list(res.embeddings[0])


@observe(name="rag.rerank")
async def _rerank(query: str, candidates: list[Citation], top_k: int) -> list[Citation]:
    """dense 検索の候補を Voyage rerank-2 で並べ替え。

    Dense 検索は「クエリの埋め込み」と「文書の埋め込み」をそれぞれ独立に作って
    距離を見る (=bi-encoder)。これは速いが、クエリと文書の **相互関係** までは
    見ていないので top-1 が外れることがある。
    Reranker は cross-encoder：クエリと各候補をペアで一緒に読ませて関連度を
    スコアリングする。精度は上がるが、N 候補なら N 回モデルを動かす（API
    呼び出し自体は 1 回にバッチされる）ぶん遅い。

    実運用としては「dense で top_k * multiplier 件を雑に集める → rerank で
    上位 top_k に絞る」のが定石。``settings.rerank_candidate_multiplier`` で
    over-fetch 量を制御。
    """
    if not candidates:
        return candidates
    res = await _voyage().rerank(
        query=query,
        documents=[c.body for c in candidates],
        model=settings.rerank_model,
        top_k=top_k,
    )
    # rerank API は元配列の index と新スコアを返してくる。
    # frozen dataclass なので ``replace`` で score だけ差し替えた新インスタンスを作る。
    return [replace(candidates[r.index], score=float(r.relevance_score)) for r in res.results]


@observe(name="rag.retrieve")
async def retrieve(query: str, top_k: int | None = None) -> list[Citation]:
    """クエリ文字列に近い法令条文を上位 K 件返す（dense ± rerank）。

    Parameters
    ----------
    query:
        日本語の質問または契約文の冒頭など。空白のみは早期 return。
    top_k:
        最終的に返す件数。``None`` の場合は ``settings.rag_top_k``。
    """
    if not query.strip():
        return []
    k = top_k if top_k is not None else settings.rag_top_k
    # rerank する場合は dense 段で多めに拾っておく（後段で絞れるように）。
    # しない場合は最終件数だけ取れば良い。
    candidate_k = k * settings.rerank_candidate_multiplier if settings.rerank_enabled else k

    embedding = await _embed_query(query)
    pool = await get_pool()
    # SQL の解説：
    # - ``c.embedding <=> $1`` が pgvector の cosine 距離演算子。
    #   $1 にバインドしたクエリベクトルと、各 chunk の embedding 列との距離。
    # - SELECT 句で ``1 - (... <=> $1)`` にして「類似度（高いほど近い）」に変換。
    # - ORDER BY を距離（昇順）にすると HNSW 索引が使われ、近似最近傍が高速。
    # - JOIN で law_documents を引いて法令タイトル・施行番号・出典 URL を同時に得る。
    # - スキーマ自体は backend (Drizzle) が SSOT。ここでは SELECT/INSERT のみ。
    rows = await pool.fetch(
        """
        SELECT
          d.id            AS law_id,
          d.title         AS law_title,
          d.law_num       AS law_num,
          d.source_url    AS source_url,
          c.article_no    AS article_no,
          c.article_title AS article_title,
          c.body          AS body,
          1 - (c.embedding <=> $1) AS score
        FROM law_chunks AS c
        JOIN law_documents AS d ON d.id = c.law_id
        ORDER BY c.embedding <=> $1
        LIMIT $2
        """,
        embedding,
        candidate_k,
    )
    candidates = [
        Citation(
            law_id=row["law_id"],
            law_title=row["law_title"],
            law_num=row["law_num"],
            article_no=row["article_no"],
            article_title=row["article_title"],
            body=row["body"],
            source_url=row["source_url"],
            score=float(row["score"]),
        )
        for row in rows
    ]

    # rerank が有効でなければ dense の結果をそのまま返す。
    # rerank 用の候補数（k * multiplier）と最終件数（k）が一致しているのでこれで OK。
    if settings.rerank_enabled and candidates:
        return await _rerank(query, candidates, k)
    return candidates
