# Graph Report - legal-ai-agent  (2026-05-04)

## Corpus Check
- 61 files · ~38,247 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 488 nodes · 952 edges · 23 communities detected
- Extraction: 63% EXTRACTED · 37% INFERRED · 0% AMBIGUOUS · INFERRED: 356 edges (avg confidence: 0.58)
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
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]

## God Nodes (most connected - your core abstractions)
1. `RequirementsDraft` - 69 edges
2. `ChatTurn` - 54 edges
3. `HearingTurnInput` - 32 edges
4. `HearingTurnResult` - 32 edges
5. `GenerateResult` - 32 edges
6. `Citation` - 32 edges
7. `EgovClient` - 16 edges
8. `retrieve()` - 15 edges
9. `VoyageEmbedder` - 13 edges
10. `traced_messages_create()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `引用候補（Citation 配列）を Claude 向けの Markdown ブロックに整形する。  このファイルが扱う AI 概念：  * **RAG inj` --uses--> `Citation`  [INFERRED]
  apps/ai/src/rag/formatter.py → apps/ai/src/rag/retriever.py
- ```Citation`` の配列を ``## 参考法令`` から始まる Markdown 文字列に整形。      出力例（簡略化）::          ##` --uses--> `Citation`  [INFERRED]
  apps/ai/src/rag/formatter.py → apps/ai/src/rag/retriever.py
- `e-Gov laws allowlist` --references--> `e-Gov 法令API v2`  [EXTRACTED]
  apps/ai/src/ingest/laws_allowlist.txt → README.md
- `sync()` --calls--> `load_dataset()`  [INFERRED]
  apps/ai/evals/sync_dataset.py → apps/ai/evals/run.py
- `load_dataset_from_langfuse()` --calls--> `get_langfuse()`  [INFERRED]
  apps/ai/evals/run.py → apps/ai/src/observability/langfuse_client.py

## Hyperedges (group relationships)
- **End-to-end contract review flow** — contracts_contractsroute, api_reviewcontract, contracts_contractsrouter, ai_client_reviewcontract, schema_contracts, schema_contractreviews, shared_types_contractreviewresult [INFERRED 0.90]
- **End-to-end chat message flow** — chat_chatroute, api_postmessage, chat_chatrouter, ai_client_chat, schema_chatthreads, schema_chatmessages, shared_types_postchatmessageresponse [INFERRED 0.90]
- **RAG law-citation pipeline** — laws_allowlist, concept_egov_lawapi, concept_voyage_voyage3, schema_lawchunks, concept_pgvector_hnsw, concept_rag_inject_block, concept_citation_bracket_id [INFERRED 0.90]
- **RAG query pipeline (embed query -> pgvector search -> format citations -> Anthropic system block)** — retriever_retrieve, retriever_embed_query, db_get_pool, formatter_format_citations, legal_chat_agent_build_rag_block, concept_anthropic_prompt_caching [INFERRED 0.90]
- **e-Gov ingest pipeline (fetch XML -> chunk -> embed -> upsert documents/chunks)** — egov_ingest_one, egov_client_egovclient, chunker_chunk_law, embedder_voyageembedder, egov_upsert_document, egov_replace_chunks [EXTRACTED 1.00]
- **Two-block system prompt: cached static prompt + uncached dynamic RAG payload** — legal_chat_agent_reply, contract_review_agent_review_contract, concept_anthropic_prompt_caching, formatter_format_citations [INFERRED 0.92]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (63): BaseSettings, _body_text(), Chunk, chunk_law(), _count_tokens(), _has_header_ancestor(), 法令 XML を Article 単位でチャンク化する。  このファイルが扱う AI 概念：  * **チャンク粒度の選択** — RAG では「埋め込み 1, 要素内の全テキストを連結して返す。空なら None。      ``itertext()`` は要素以下の全テキストノードを順に返すジェネレータ。     ヘッ (+55 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (47): _block_to_dict(), _client(), _execute_search_laws(), _format_search_result(), ReAct スタイルの法務リサーチエージェント。  このファイルが扱う AI 概念：  * **ReAct (Reason + Act) loop** — モデ, Anthropic 非同期クライアントのプロセス内シングルトン。HTTP 接続を使い回す。, 検索結果をモデルが読みやすい **テキスト** に整形する。      モデルに渡す ``tool_result`` の content は文字列でも構造体でも, ``search_laws`` ツール本体。引数を検証して RAG retriever に流す。      モデルが渡してくる ``tool_input`` は (+39 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (64): NDA ドラフトに必要な要件の「現状埋まっている分」。      * Python 内部は snake_case 属性 (PEP 8)、JSON 入出力は ca, RequirementsDraft, ChatTurn, 1 ターン分の発話。``role`` は user / assistant のどちらか。      Anthropic Messages API の ``mes, _count_forbidden_hits(), EvalCase, filter_cases_by_agent(), _judge_client() (+56 more)

### Community 3 - "Community 3"
Cohesion: 0.1
Nodes (56): GenerateResult, HearingTurnInput, HearingTurnResult, ``hearing_turn()`` の入力。1 ターン分のメッセージ + 既知の要件。, ``hearing_turn()`` の出力。Assistant の発話と更新後の要件。, ``generate_full_draft()`` の出力。3 phase 分の成果物 + 計装メタ。, draft_node(), generate_from_requirements_v2() (+48 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (29): _block_to_dict(), _build_rag_block(), _client(), generate_from_requirements(), generate_full_draft(), hearing_turn(), NDA ドラフト生成用のワークフロー型エージェント。  このファイルが扱う AI 概念：  * **Multi-phase agentic workflow**, None / 空文字 / 0 を「未入力」、それ以外を「入力済み」と扱う。      ``term_months`` は 0 だと有効期間が無くなるので、これも (+21 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (12): request(), requestMultipart(), action(), assignFile(), handleDrop(), chat(), draftGenerateFull(), draftGenerateFullV2() (+4 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (24): _build_rag_block(), _client(), 契約書レビュー用エージェント（強制 tool 呼び出しによる構造化出力）。  このファイルが扱う AI 概念：  * **Tool use as structu, 契約タイトル + 本文先頭 800 字を retrieval クエリにする。      契約全文（数千〜数万字）をそのまま埋め込みクエリに使うと、     -, RAG ブロック（``## 参考法令``）を組み立てる。失敗時は空文字に縮退。      ``legal_chat._build_rag_block`` と同じ, 契約書を Claude にレビューさせ、構造化レポートを返す。      フロー:      1. RAG で参考法令を取得（縮退あり）     2. syst, Anthropic 非同期クライアントのプロセス内シングルトン。, _retrieval_query() (+16 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (22): main(), ``evals/dataset.jsonl`` を Langfuse Dataset として upsert する CLI。  このファイルが扱う AI 概念：, JSONL の各ケースを Langfuse Dataset アイテムとして upsert する。, sync(), Langfuse による LLM observability の薄いラッパ層。  外側からはこのパッケージ経由でだけ Langfuse に触る。 ``setti, flush_langfuse(), get_langfuse(), observe() (+14 more)

### Community 8 - "Community 8"
Cohesion: 0.14
Nodes (16): _build_rag_block(), _client(), 法務相談チャット用エージェント（RAG 注入 + 1-shot 生成パターン）。  このファイルが扱う AI 概念：  * **RAG injection (1, system プロンプトの Markdown を 1 度だけ読んでメモリ常駐させる。      ``lru_cache(maxsize=1)`` は実質「プロセ, Anthropic 非同期クライアントを 1 つだけ作って使い回す。      ``AsyncAnthropic`` は内部で HTTP コネクションプールを保, RAG ブロック（``## 参考法令`` から始まる Markdown）を組み立てる。      設計判断：      * RAG が無効、またはクエリが空なら, 会話履歴を受け取り、Claude の応答テキストを返す。      フロー:      1. 最新 user 発話をクエリに RAG 検索（``_build_r, reply() (+8 more)

### Community 9 - "Community 9"
Cohesion: 0.16
Nodes (18): Anthropic Claude (claude-opus-4-7), [番号] citation format, 独占禁止法 (322AC0000000054), e-Gov 法令API v2, 会社法 (417AC0000000086), 個人情報保護法 (415AC0000000057), 民法 (129AC0000000089), pgvector HNSW cosine index (+10 more)

### Community 10 - "Community 10"
Cohesion: 0.2
Nodes (9): post_research(), ReAct リサーチエージェント用の FastAPI ルータ。  このルータは ``agents/research_agent.py`` の ``researc, ``POST /research`` の入力スキーマ。      Field の制約はリクエスト境界での DoS 対策も兼ねる：     - question, ReAct ループ中に ``search_laws`` で引いた条文 1 件分。      フィールドは ``rag/retriever.py`` の ``Ci, ``POST /research`` の出力スキーマ。``iterations`` で何往復したか分かる。      ``citations`` は ReAct, ReAct ループを起動して最終回答を返す。, ResearchCitation, ResearchRequest (+1 more)

### Community 11 - "Community 11"
Cohesion: 0.5
Nodes (4): main(), 契約書レビュー機能の動作確認用に、サンプル NDA PDF を生成するスクリプト。  reportlab は本番依存ではなく、このスクリプト専用なので uv の, 日本語の横書きを max_width で折り返して描画。次の y を返す。, _wrap()

### Community 15 - "Community 15"
Cohesion: 0.5
Nodes (3): Embedder, 埋め込み実装が満たすべきインターフェイス（型ヒント目的）。      Protocol はランタイム継承不要：このシグネチャを持つ任意のクラスが     自動で, Protocol

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (1): Shared test setup: stub required envs before src.config is imported.

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): アプリの起動 / 停止に紐づく副作用を集約する。      - startup: RAG が有効なら pgvector 用の DB プールを温めておく

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): 死活監視用の最軽量エンドポイント。      意図的に DB やモデルには触れない（外部サービス障害時にも 200 を返す）。     モニタリングは「プロセス

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Approximate token count. Uses tiktoken when available, falls back to len/2.

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Walk e-Gov 法令 XML and emit one Chunk per <Article>, splitting long ones.      Th

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): Concatenate non-empty text nodes under Article, skipping header elements.

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): e-Gov v2: GET /law_data/{law_id} → 法令本文 XML.

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Lazy import to keep test/import cost low.

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): 契約タイトル + 本文先頭 800 字を retrieval クエリにする。

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Schema SSOT rule (Drizzle owns DDL)

## Knowledge Gaps
- **107 isolated node(s):** ```evals/dataset.jsonl`` を Langfuse Dataset として upsert する CLI。  このファイルが扱う AI 概念：`, `JSONL の各ケースを Langfuse Dataset アイテムとして upsert する。`, `Shared test setup: stub required envs before src.config is imported.`, `契約書レビュー機能の動作確認用に、サンプル NDA PDF を生成するスクリプト。  reportlab は本番依存ではなく、このスクリプト専用なので uv の`, `日本語の横書きを max_width で折り返して描画。次の y を返す。` (+102 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 18`** (2 nodes): `conftest.py`, `Shared test setup: stub required envs before src.config is imported.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `アプリの起動 / 停止に紐づく副作用を集約する。      - startup: RAG が有効なら pgvector 用の DB プールを温めておく`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `死活監視用の最軽量エンドポイント。      意図的に DB やモデルには触れない（外部サービス障害時にも 200 を返す）。     モニタリングは「プロセス`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Approximate token count. Uses tiktoken when available, falls back to len/2.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `Walk e-Gov 法令 XML and emit one Chunk per <Article>, splitting long ones.      Th`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `Concatenate non-empty text nodes under Article, skipping header elements.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `e-Gov v2: GET /law_data/{law_id} → 法令本文 XML.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `Lazy import to keep test/import cost low.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `契約タイトル + 本文先頭 800 字を retrieval クエリにする。`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `Schema SSOT rule (Drizzle owns DDL)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Citation` connect `Community 1` to `Community 8`, `Community 6`?**
  _High betweenness centrality (0.152) - this node is a cross-community bridge._
- **Why does `retrieve()` connect `Community 1` to `Community 0`, `Community 4`, `Community 5`, `Community 6`, `Community 8`?**
  _High betweenness centrality (0.123) - this node is a cross-community bridge._
- **Why does `ChatTurn` connect `Community 2` to `Community 8`, `Community 3`?**
  _High betweenness centrality (0.118) - this node is a cross-community bridge._
- **Are the 64 inferred relationships involving `RequirementsDraft` (e.g. with `EvalCase` and `Eval harness for the legal AI agents.  このファイルが扱う AI 概念：  * **Eval（評価ハーネス）の意義** —`) actually correct?**
  _`RequirementsDraft` has 64 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `ChatTurn` (e.g. with `EvalCase` and `Eval harness for the legal AI agents.  このファイルが扱う AI 概念：  * **Eval（評価ハーネス）の意義** —`) actually correct?**
  _`ChatTurn` has 51 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `HearingTurnInput` (e.g. with `HearingHistoryItem` and `HearingRequest`) actually correct?**
  _`HearingTurnInput` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `HearingTurnResult` (e.g. with `HearingHistoryItem` and `HearingRequest`) actually correct?**
  _`HearingTurnResult` has 28 INFERRED edges - model-reasoned connections that need verification._