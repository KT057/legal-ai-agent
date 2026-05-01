# Graph Report - ai  (2026-05-01)

## Corpus Check
- 31 files · ~10,007 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 269 nodes · 454 edges · 15 communities detected
- Extraction: 72% EXTRACTED · 28% INFERRED · 0% AMBIGUOUS · INFERRED: 128 edges (avg confidence: 0.6)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]

## God Nodes (most connected - your core abstractions)
1. `Citation` - 38 edges
2. `ChatTurn` - 29 edges
3. `EgovClient` - 16 edges
4. `retrieve()` - 14 edges
5. `VoyageEmbedder` - 13 edges
6. `Chunk` - 10 edges
7. `chunk_law()` - 10 edges
8. `FetchedLaw` - 10 edges
9. `research()` - 10 edges
10. `reply()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `Verify the reranker path: over-fetch → rerank → take top K with new scores.` --uses--> `Citation`  [INFERRED]
  tests/test_retriever_rerank.py → src/rag/retriever.py
- `Unit test for the retriever — mocks Voyage and asyncpg pool.` --uses--> `Citation`  [INFERRED]
  tests/test_retriever.py → src/rag/retriever.py
- `Eval harness for the legal AI agents.  このファイルが扱う AI 概念：  * **Eval（評価ハーネス）の意義** —` --uses--> `ChatTurn`  [INFERRED]
  evals/run.py → src/agents/legal_chat.py
- `1 件の golden ケース。      Fields:         id: ケースの一意 ID（レポート表示と差分追跡に使う）         ques` --uses--> `ChatTurn`  [INFERRED]
  evals/run.py → src/agents/legal_chat.py
- `JSONL を 1 行 1 ケースで読み込む。      JSONL を選んでいるのは、追加・差分・PR レビューがしやすいため。     1 ケース 1 行な` --uses--> `ChatTurn`  [INFERRED]
  evals/run.py → src/agents/legal_chat.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (44): _body_text(), Chunk, chunk_law(), _count_tokens(), _has_header_ancestor(), 法令 XML を Article 単位でチャンク化する。  このファイルが扱う AI 概念：  * **チャンク粒度の選択** — RAG では「埋め込み 1, 要素内の全テキストを連結して返す。空なら None。      ``itertext()`` は要素以下の全テキストノードを順に返すジェネレータ。     ヘッ, Concatenate non-empty text nodes under Article, skipping header elements.      X (+36 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (29): _block_to_dict(), _client(), _execute_search_laws(), _format_search_result(), ReAct スタイルの法務リサーチエージェント。  このファイルが扱う AI 概念：  * **ReAct (Reason + Act) loop** — モデ, Anthropic 非同期クライアントのプロセス内シングルトン。HTTP 接続を使い回す。, 検索結果をモデルが読みやすい **テキスト** に整形する。      モデルに渡す ``tool_result`` の content は文字列でも構造体でも, ``search_laws`` ツール本体。引数を検証して RAG retriever に流す。      モデルが渡してくる ``tool_input`` は (+21 more)

### Community 2 - "Community 2"
Cohesion: 0.11
Nodes (31): ChatTurn, 1 ターン分の発話。``role`` は user / assistant のどちらか。      Anthropic Messages API の ``mes, EvalCase, _judge_client(), load_dataset(), main(), Eval harness for the legal AI agents.  このファイルが扱う AI 概念：  * **Eval（評価ハーネス）の意義** —, legal_chat (1-shot) を実行して標準 trace 形式に詰める。      legal_chat は ``iterations`` の概念がな (+23 more)

### Community 3 - "Community 3"
Cohesion: 0.1
Nodes (22): BaseModel, post_review(), 契約書レビュー用の FastAPI ルータ。  このルータも ``agents/contract_review.py`` の ``review_contract, 1 件のリスク指摘。``severity`` の値域は Literal で保証。      エージェント側の REPORT_TOOL の input_schem, ``POST /review`` の出力スキーマ。総評と複数のリスク。, 契約書テキスト or PDF を Claude に投げ、構造化されたレビュー結果を返す。      file が指定されていれば PDF からテキストを抽出して, body / file から最終的な契約本文テキストを決める。      優先順位: file > body。どちらも無ければ 400。, _resolve_body_text() (+14 more)

### Community 4 - "Community 4"
Cohesion: 0.13
Nodes (16): _embed_query(), 法令検索（RAG retriever）— クエリ → 埋め込み → pgvector → (任意で rerank)。  このファイルが扱う AI 概念：  *, クエリ文字列に近い法令条文を上位 K 件返す（dense ± rerank）。      Parameters     ----------     query, Voyage の非同期クライアントをプロセス内シングルトン化して接続を再利用。, 検索クエリを埋め込みベクトル（``embedding_dim`` 次元）に変換する。      ``input_type="query"`` がポイント。ing, dense 検索の候補を Voyage rerank-2 で並べ替え。      Dense 検索は「クエリの埋め込み」と「文書の埋め込み」をそれぞれ独立に作っ, _rerank(), retrieve() (+8 more)

### Community 5 - "Community 5"
Cohesion: 0.13
Nodes (16): _build_rag_block(), _client(), 法務相談チャット用エージェント（RAG 注入 + 1-shot 生成パターン）。  このファイルが扱う AI 概念：  * **RAG injection (1, system プロンプトの Markdown を 1 度だけ読んでメモリ常駐させる。      ``lru_cache(maxsize=1)`` は実質「プロセ, Anthropic 非同期クライアントを 1 つだけ作って使い回す。      ``AsyncAnthropic`` は内部で HTTP コネクションプールを保, RAG ブロック（``## 参考法令`` から始まる Markdown）を組み立てる。      設計判断：      * RAG が無効、またはクエリが空なら, 会話履歴を受け取り、Claude の応答テキストを返す。      フロー:      1. 最新 user 発話をクエリに RAG 検索（``_build_r, reply() (+8 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (16): BaseSettings, close_pool(), get_pool(), _init_conn(), pgvector 対応 PostgreSQL コネクションプール。  このファイルが扱う AI 概念：  * **asyncpg + pgvector** —, プールから新しいコネクションが払い出される度に呼ばれるフック。      asyncpg のコネクションごとに pgvector 拡張型を登録しないと、, シングルトンのコネクションプールを返す（無ければ作る）。      ``min_size=1, max_size=5`` は本リポジトリ規模での実用値。, プールを閉じる。FastAPI lifespan の shutdown フェーズで呼ばれる。 (+8 more)

### Community 7 - "Community 7"
Cohesion: 0.19
Nodes (8): _FakePool, _FakeVoyageWithRerank, Verify the reranker path: over-fetch → rerank → take top K with new scores., _RerankResponse, _RerankResult, _row(), test_rerank_disabled_skips_voyage_rerank(), test_rerank_overfetches_and_reorders()

### Community 8 - "Community 8"
Cohesion: 0.17
Nodes (14): _build_rag_block(), _client(), 契約書レビュー用エージェント（強制 tool 呼び出しによる構造化出力）。  このファイルが扱う AI 概念：  * **Tool use as structu, RAG ブロック（``## 参考法令``）を組み立てる。失敗時は空文字に縮退。      ``legal_chat._build_rag_block`` と同じ, 契約書を Claude にレビューさせ、構造化レポートを返す。      フロー:      1. RAG で参考法令を取得（縮退あり）     2. syst, 契約書レビュー用の system プロンプト Markdown を 1 度だけ読む。, Anthropic 非同期クライアントのプロセス内シングルトン。, 契約タイトル + 本文先頭 800 字を retrieval クエリにする。      契約全文（数千〜数万字）をそのまま埋め込みクエリに使うと、     - (+6 more)

### Community 9 - "Community 9"
Cohesion: 0.25
Nodes (6): default_embedder(), Embedder, Voyage 埋め込みクライアント（ingest 側 = ``input_type="document"``）。  このファイルが扱う AI 概念：  * **, 埋め込み実装が満たすべきインターフェイス（型ヒント目的）。      Protocol はランタイム継承不要：このシグネチャを持つ任意のクラスが     自動で, プロセス内で 1 つの ``VoyageEmbedder`` を共有する取り出し口。      HTTP クライアントの再利用と、テストでの差し替えポイントを兼, Protocol

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (1): Shared test setup: stub required envs before src.config is imported.

### Community 19 - "Community 19"
Cohesion: 1.0
Nodes (1): ``POST /review`` の入力スキーマ。      body の上限 200,000 字は概ね 60〜80 ページ相当の契約まで対応できる想定。

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (1): 1 件のリスク指摘。``severity`` の値域は Literal で保証。      エージェント側の REPORT_TOOL の input_schem

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (1): ``POST /review`` の出力スキーマ。総評と複数のリスク。

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (1): 契約書テキストを Claude に投げ、構造化されたレビュー結果を返す。

## Knowledge Gaps
- **70 isolated node(s):** `Shared test setup: stub required envs before src.config is imported.`, `アプリ全体の設定値（環境変数 → typed Settings）。  このファイルが扱う AI 概念：  * **pydantic-settings** — 環`, `環境変数から読み込む設定値の型付きコンテナ。`, `FastAPI アプリのエントリポイント。  このファイルが扱う AI 概念：  * **FastAPI lifespan** — アプリ起動時 / 停止時に走`, `アプリの起動 / 停止に紐づく副作用を集約する。      - startup: RAG が有効なら pgvector 用の DB プールを温めておく` (+65 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 10`** (2 nodes): `conftest.py`, `Shared test setup: stub required envs before src.config is imported.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 19`** (1 nodes): ```POST /review`` の入力スキーマ。      body の上限 200,000 字は概ね 60〜80 ページ相当の契約まで対応できる想定。`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 20`** (1 nodes): `1 件のリスク指摘。``severity`` の値域は Literal で保証。      エージェント側の REPORT_TOOL の input_schem`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (1 nodes): ```POST /review`` の出力スキーマ。総評と複数のリスク。`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (1 nodes): `契約書テキストを Claude に投げ、構造化されたレビュー結果を返す。`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Citation` connect `Community 1` to `Community 8`, `Community 4`, `Community 5`, `Community 7`?**
  _High betweenness centrality (0.314) - this node is a cross-community bridge._
- **Why does `ChatTurn` connect `Community 2` to `Community 3`, `Community 5`?**
  _High betweenness centrality (0.198) - this node is a cross-community bridge._
- **Why does `retrieve()` connect `Community 4` to `Community 1`, `Community 5`, `Community 6`, `Community 7`, `Community 8`?**
  _High betweenness centrality (0.095) - this node is a cross-community bridge._
- **Are the 35 inferred relationships involving `Citation` (e.g. with `_FakePool` and `_RerankResult`) actually correct?**
  _`Citation` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `ChatTurn` (e.g. with `EvalCase` and `Eval harness for the legal AI agents.  このファイルが扱う AI 概念：  * **Eval（評価ハーネス）の意義** —`) actually correct?**
  _`ChatTurn` has 26 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `EgovClient` (e.g. with `e-Gov 法令データを取り込んで Postgres + pgvector に保存する CLI.  このファイルが扱う AI 概念：  * **RAG inge` and `allowlist テキストを読んで LawId のリストにする。      フォーマット（``laws_allowlist.txt`` 参照）:     -`) actually correct?**
  _`EgovClient` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `retrieve()` (e.g. with `test_rerank_overfetches_and_reorders()` and `test_rerank_disabled_skips_voyage_rerank()`) actually correct?**
  _`retrieve()` has 9 INFERRED edges - model-reasoned connections that need verification._