# Graph Report - legal-ai-agent  (2026-05-04)

## Corpus Check
- 59 files · ~24,508 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 432 nodes · 777 edges · 19 communities detected
- Extraction: 71% EXTRACTED · 29% INFERRED · 0% AMBIGUOUS · INFERRED: 229 edges (avg confidence: 0.6)
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
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]

## God Nodes (most connected - your core abstractions)
1. `ChatTurn` - 36 edges
2. `RequirementsDraft` - 36 edges
3. `Citation` - 32 edges
4. `EgovClient` - 16 edges
5. `HearingTurnInput` - 16 edges
6. `HearingTurnResult` - 16 edges
7. `GenerateResult` - 16 edges
8. `retrieve()` - 15 edges
9. `VoyageEmbedder` - 13 edges
10. `traced_messages_create()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `Verify the reranker path: over-fetch → rerank → take top K with new scores.` --uses--> `Citation`  [INFERRED]
  apps/ai/tests/test_retriever_rerank.py → apps/ai/src/rag/retriever.py
- `Tests for the ReAct research agent.  Verifies the loop: model emits tool_use → a` --uses--> `Citation`  [INFERRED]
  apps/ai/tests/test_research_agent.py → apps/ai/src/rag/retriever.py
- `ReAct スタイルの法務リサーチエージェント。  このファイルが扱う AI 概念：  * **ReAct (Reason + Act) loop** — モデ` --uses--> `Citation`  [INFERRED]
  apps/ai/src/agents/research_agent.py → apps/ai/src/rag/retriever.py
- `Anthropic 非同期クライアントのプロセス内シングルトン。HTTP 接続を使い回す。` --uses--> `Citation`  [INFERRED]
  apps/ai/src/agents/research_agent.py → apps/ai/src/rag/retriever.py
- `検索結果をモデルが読みやすい **テキスト** に整形する。      モデルに渡す ``tool_result`` の content は文字列でも構造体でも` --uses--> `Citation`  [INFERRED]
  apps/ai/src/agents/research_agent.py → apps/ai/src/rag/retriever.py

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
Nodes (67): ChatTurn, 1 ターン分の発話。``role`` は user / assistant のどちらか。      Anthropic Messages API の ``mes, _count_forbidden_hits(), EvalCase, filter_cases_by_agent(), _judge_client(), _langfuse_dataset_url(), load_dataset() (+59 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (48): _build_rag_block(), _client(), 契約書レビュー用エージェント（強制 tool 呼び出しによる構造化出力）。  このファイルが扱う AI 概念：  * **Tool use as structu, 契約タイトル + 本文先頭 800 字を retrieval クエリにする。      契約全文（数千〜数万字）をそのまま埋め込みクエリに使うと、     -, RAG ブロック（``## 参考法令``）を組み立てる。失敗時は空文字に縮退。      ``legal_chat._build_rag_block`` と同じ, 契約書を Claude にレビューさせ、構造化レポートを返す。      フロー:      1. RAG で参考法令を取得（縮退あり）     2. syst, 契約書レビュー用の system プロンプト Markdown を 1 度だけ読む。, Anthropic 非同期クライアントのプロセス内シングルトン。 (+40 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (51): _block_to_dict(), _build_rag_block(), _client(), generate_from_requirements(), generate_full_draft(), GenerateResult, hearing_turn(), HearingTurnInput (+43 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (30): _block_to_dict(), _client(), _execute_search_laws(), _format_search_result(), ReAct スタイルの法務リサーチエージェント。  このファイルが扱う AI 概念：  * **ReAct (Reason + Act) loop** — モデ, Anthropic 非同期クライアントのプロセス内シングルトン。HTTP 接続を使い回す。, 検索結果をモデルが読みやすい **テキスト** に整形する。      モデルに渡す ``tool_result`` の content は文字列でも構造体でも, ``search_laws`` ツール本体。引数を検証して RAG retriever に流す。      モデルが渡してくる ``tool_input`` は (+22 more)

### Community 5 - "Community 5"
Cohesion: 0.12
Nodes (10): request(), requestMultipart(), action(), assignFile(), handleDrop(), chat(), draftGenerateFull(), draftHearingTurn() (+2 more)

### Community 6 - "Community 6"
Cohesion: 0.16
Nodes (18): Anthropic Claude (claude-opus-4-7), [番号] citation format, 独占禁止法 (322AC0000000054), e-Gov 法令API v2, 会社法 (417AC0000000086), 個人情報保護法 (415AC0000000057), 民法 (129AC0000000089), pgvector HNSW cosine index (+10 more)

### Community 7 - "Community 7"
Cohesion: 0.19
Nodes (8): _FakePool, _FakeVoyageWithRerank, Verify the reranker path: over-fetch → rerank → take top K with new scores., _RerankResponse, _RerankResult, _row(), test_rerank_disabled_skips_voyage_rerank(), test_rerank_overfetches_and_reorders()

### Community 8 - "Community 8"
Cohesion: 0.16
Nodes (12): post_review(), 契約書レビュー用の FastAPI ルータ。  このルータは ``agents/contract_review.py`` の ``review_contract, 1 件のリスク指摘。``severity`` の値域は Literal で保証。      エージェント側の REPORT_TOOL の input_schem, ``POST /review`` の出力スキーマ。総評と複数のリスク。, 契約書テキスト or PDF を Claude に投げ、構造化されたレビュー結果を返す。      file が指定されていれば PDF からテキストを抽出して, body / file から最終的な契約本文テキストを決める。      優先順位: file > body。どちらも無ければ 400。, _resolve_body_text(), ReviewedRisk (+4 more)

### Community 10 - "Community 10"
Cohesion: 0.5
Nodes (4): main(), 契約書レビュー機能の動作確認用に、サンプル NDA PDF を生成するスクリプト。  reportlab は本番依存ではなく、このスクリプト専用なので uv の, 日本語の横書きを max_width で折り返して描画。次の y を返す。, _wrap()

### Community 13 - "Community 13"
Cohesion: 0.5
Nodes (3): Embedder, 埋め込み実装が満たすべきインターフェイス（型ヒント目的）。      Protocol はランタイム継承不要：このシグネチャを持つ任意のクラスが     自動で, Protocol

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Shared test setup: stub required envs before src.config is imported.

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): Approximate token count. Uses tiktoken when available, falls back to len/2.

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): Walk e-Gov 法令 XML and emit one Chunk per <Article>, splitting long ones.      Th

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): Concatenate non-empty text nodes under Article, skipping header elements.

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): e-Gov v2: GET /law_data/{law_id} → 法令本文 XML.

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Lazy import to keep test/import cost low.

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): 契約タイトル + 本文先頭 800 字を retrieval クエリにする。

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): Schema SSOT rule (Drizzle owns DDL)

## Knowledge Gaps
- **105 isolated node(s):** ```evals/dataset.jsonl`` を Langfuse Dataset として upsert する CLI。  このファイルが扱う AI 概念：`, `JSONL の各ケースを Langfuse Dataset アイテムとして upsert する。`, `Shared test setup: stub required envs before src.config is imported.`, `契約書レビュー機能の動作確認用に、サンプル NDA PDF を生成するスクリプト。  reportlab は本番依存ではなく、このスクリプト専用なので uv の`, `日本語の横書きを max_width で折り返して描画。次の y を返す。` (+100 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 16`** (2 nodes): `conftest.py`, `Shared test setup: stub required envs before src.config is imported.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `Approximate token count. Uses tiktoken when available, falls back to len/2.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `Walk e-Gov 法令 XML and emit one Chunk per <Article>, splitting long ones.      Th`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `Concatenate non-empty text nodes under Article, skipping header elements.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `e-Gov v2: GET /law_data/{law_id} → 法令本文 XML.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Lazy import to keep test/import cost low.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `契約タイトル + 本文先頭 800 字を retrieval クエリにする。`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `Schema SSOT rule (Drizzle owns DDL)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Citation` connect `Community 2` to `Community 4`, `Community 7`?**
  _High betweenness centrality (0.164) - this node is a cross-community bridge._
- **Why does `retrieve()` connect `Community 2` to `Community 0`, `Community 3`, `Community 4`, `Community 5`, `Community 7`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Why does `ChatTurn` connect `Community 1` to `Community 2`, `Community 3`?**
  _High betweenness centrality (0.100) - this node is a cross-community bridge._
- **Are the 33 inferred relationships involving `ChatTurn` (e.g. with `EvalCase` and `Eval harness for the legal AI agents.  このファイルが扱う AI 概念：  * **Eval（評価ハーネス）の意義** —`) actually correct?**
  _`ChatTurn` has 33 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `RequirementsDraft` (e.g. with `EvalCase` and `Eval harness for the legal AI agents.  このファイルが扱う AI 概念：  * **Eval（評価ハーネス）の意義** —`) actually correct?**
  _`RequirementsDraft` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `Citation` (e.g. with `_FakePool` and `_RerankResult`) actually correct?**
  _`Citation` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `EgovClient` (e.g. with `e-Gov 法令データを取り込んで Postgres + pgvector に保存する CLI.  Usage:     uv run python -m sr` and `allowlist テキストを読んで LawId のリストにする。      フォーマット（``laws_allowlist.txt`` 参照）:     -`) actually correct?**
  _`EgovClient` has 8 INFERRED edges - model-reasoned connections that need verification._