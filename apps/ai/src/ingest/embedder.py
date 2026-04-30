"""Voyage 埋め込みクライアント（ingest 側 = ``input_type="document"``）。

このファイルが扱う AI 概念：

* **Protocol（構造的サブタイピング）** — ``Embedder`` は ABC ではなく
  ``typing.Protocol``。「``embed_documents`` を持つ任意のクラス」を
  Embedder とみなせる（duck typing の型ヒント版）。
  テストで ``FakeEmbedder`` を差し込むのに継承が要らないのが利点。
* **バッチ埋め込み** — Voyage の embed API は 1 リクエストで複数テキストを送れる。
  1 件ずつ呼ぶと API 呼び出し数 = チャンク数となりレイテンシが線形に伸びる。
  128 件単位でまとめると API レイテンシが大幅に減り、料金計算も予測しやすい。
* **input_type の非対称性** — ingest は ``"document"``、検索は ``"query"``。
  Voyage（や OpenAI/Cohere の一部モデル）はクエリ埋め込みと文書埋め込みを
  非対称にチューニングしているため、保存と検索で正しい input_type を
  指定すると精度が上がる。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

import voyageai

from ..config import settings


class Embedder(Protocol):
    """埋め込み実装が満たすべきインターフェイス（型ヒント目的）。

    Protocol はランタイム継承不要：このシグネチャを持つ任意のクラスが
    自動で「Embedder のサブタイプ」とみなされる。テスト時に Voyage を
    モックに差し替える際に便利。
    """

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class VoyageEmbedder:
    """Voyage AI を使った埋め込み実装（ingest 用）。"""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._client = voyageai.AsyncClient(api_key=api_key or settings.voyage_api_key)
        self._model = model or settings.embedding_model
        # 1 リクエストあたりの最大件数。
        # 大きすぎると API 側でリジェクト or タイムアウト、
        # 小さすぎると呼び出し回数が増えて遅い。128 は経験則的なバランス。
        self._batch_size = 128

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """テキスト配列を埋め込みベクトルの配列に変換する（順序保存）。

        実装詳細:
        - ``range(0, len(texts), batch_size)`` で 128 件ずつスライス
        - 各バッチで ``embed(input_type="document")`` を呼ぶ
        - 戻り値の embeddings を **入力と同順序** で連結
        """
        out: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            res = await self._client.embed(
                texts=batch,
                model=self._model,
                # ingest 側なので "document"。検索時 (retriever._embed_query)
                # は "query" を渡しており、対称型ではなく **非対称検索** になる。
                input_type="document",
            )
            out.extend(list(v) for v in res.embeddings)
        return out


@lru_cache(maxsize=1)
def default_embedder() -> Embedder:
    """プロセス内で 1 つの ``VoyageEmbedder`` を共有する取り出し口。

    HTTP クライアントの再利用と、テストでの差し替えポイントを兼ねる。
    """
    return VoyageEmbedder()
