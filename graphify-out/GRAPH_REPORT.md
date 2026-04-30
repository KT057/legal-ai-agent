# Graph Report - .  (2026-04-29)

## Corpus Check
- Corpus is ~6,745 words - fits in a single context window. You may not need a graph.

## Summary
- 266 nodes · 392 edges · 20 communities detected
- Extraction: 81% EXTRACTED · 19% INFERRED · 0% AMBIGUOUS · INFERRED: 74 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Legal Doc Chunking|Legal Doc Chunking]]
- [[_COMMUNITY_AI App Bootstrap & Ingest|AI App Bootstrap & Ingest]]
- [[_COMMUNITY_Frontend API Client|Frontend API Client]]
- [[_COMMUNITY_Legal Chat Agent|Legal Chat Agent]]
- [[_COMMUNITY_External Services & Laws|External Services & Laws]]
- [[_COMMUNITY_RAG Retrieval|RAG Retrieval]]
- [[_COMMUNITY_Contract Review Tooling|Contract Review Tooling]]
- [[_COMMUNITY_Chunker Tests|Chunker Tests]]
- [[_COMMUNITY_Backend API (Hono)|Backend API (Hono)]]
- [[_COMMUNITY_Contract Review Agent|Contract Review Agent]]
- [[_COMMUNITY_Pytest Fixtures|Pytest Fixtures]]
- [[_COMMUNITY_Chat Schemas|Chat Schemas]]
- [[_COMMUNITY_Layout Component|Layout Component]]
- [[_COMMUNITY_App Component|App Component]]
- [[_COMMUNITY_ErrorBoundary|ErrorBoundary]]
- [[_COMMUNITY_Vite Frontend Config|Vite Frontend Config]]
- [[_COMMUNITY_React Router SSR Config|React Router SSR Config]]
- [[_COMMUNITY_Fake Anthropic Stub|Fake Anthropic Stub]]
- [[_COMMUNITY_ChatResponse Schema|ChatResponse Schema]]
- [[_COMMUNITY_ReviewRequest Schema|ReviewRequest Schema]]

## God Nodes (most connected - your core abstractions)
1. `ChatTurn` - 11 edges
2. `Citation` - 11 edges
3. `chunk_law()` - 10 edges
4. `chatRouter (Hono)` - 10 edges
5. `retrieve` - 10 edges
6. `EgovClient` - 9 edges
7. `retrieve()` - 9 edges
8. `reply()` - 8 edges
9. `chunk_law` - 8 edges
10. `reply` - 8 edges

## Surprising Connections (you probably didn't know these)
- `RAG ## 参考法令 system block injection` --shares_data_with--> `law_chunks table (pgvector hnsw)`  [INFERRED]
  README.md → apps/backend/src/db/schema.ts
- `RAG ## 参考法令 system block injection` --conceptually_related_to--> `reviewContract (AI client)`  [INFERRED]
  README.md → apps/backend/src/services/ai-client.ts
- `RAG ## 参考法令 system block injection` --conceptually_related_to--> `chat (AI client)`  [INFERRED]
  README.md → apps/backend/src/services/ai-client.ts
- `chat (AI client)` --shares_data_with--> `ChatMessage`  [EXTRACTED]
  apps/backend/src/services/ai-client.ts → packages/shared-types/src/index.ts
- `Schema SSOT rule (Drizzle owns DDL)` --rationale_for--> `contracts table`  [EXTRACTED]
  apps/ai/src/rag/README.md → apps/backend/src/db/schema.ts

## Hyperedges (group relationships)
- **End-to-end contract review flow** — contracts_contractsroute, api_reviewcontract, contracts_contractsrouter, ai_client_reviewcontract, schema_contracts, schema_contractreviews, shared_types_contractreviewresult [INFERRED 0.90]
- **End-to-end chat message flow** — chat_chatroute, api_postmessage, chat_chatrouter, ai_client_chat, schema_chatthreads, schema_chatmessages, shared_types_postchatmessageresponse [INFERRED 0.90]
- **RAG law-citation pipeline** — laws_allowlist, concept_egov_lawapi, concept_voyage_voyage3, schema_lawchunks, concept_pgvector_hnsw, concept_rag_inject_block, concept_citation_bracket_id [INFERRED 0.90]
- **RAG query pipeline (embed query -> pgvector search -> format citations -> Anthropic system block)** — retriever_retrieve, retriever_embed_query, db_get_pool, formatter_format_citations, legal_chat_agent_build_rag_block, concept_anthropic_prompt_caching [INFERRED 0.90]
- **e-Gov ingest pipeline (fetch XML -> chunk -> embed -> upsert documents/chunks)** — egov_ingest_one, egov_client_egovclient, chunker_chunk_law, embedder_voyageembedder, egov_upsert_document, egov_replace_chunks [EXTRACTED 1.00]
- **Two-block system prompt: cached static prompt + uncached dynamic RAG payload** — legal_chat_agent_reply, contract_review_agent_review_contract, concept_anthropic_prompt_caching, formatter_format_citations [INFERRED 0.92]

## Communities

### Community 0 - "Legal Doc Chunking"
Cohesion: 0.06
Nodes (41): _body_text, Chunk, chunk_law, _count_tokens, _has_header_ancestor, _text_of, _window_split, law_chunks (Postgres table) (+33 more)

### Community 1 - "AI App Bootstrap & Ingest"
Cohesion: 0.09
Nodes (22): BaseSettings, _build_arg_parser(), EgovClient, FetchedLaw, _parse_law_meta(), e-Gov v2: GET /law_data/{law_id} → 法令本文 XML., Lazy import to keep test/import cost low., ingest_one() (+14 more)

### Community 2 - "Frontend API Client"
Cohesion: 0.11
Nodes (29): IndexRoute component, frontend api client, api.createThread, api.getThread, api.listThreads, api.postMessage, request, api.reviewContract (+21 more)

### Community 3 - "Legal Chat Agent"
Cohesion: 0.14
Nodes (21): _build_rag_block(), ChatTurn, _client(), reply(), _system_prompt(), BaseModel, Citation, post_review() (+13 more)

### Community 4 - "External Services & Laws"
Cohesion: 0.13
Nodes (24): chat (AI client), reviewContract (AI client), Anthropic Claude (claude-opus-4-7), [番号] citation format, 独占禁止法 (322AC0000000054), e-Gov 法令API v2, 会社法 (417AC0000000086), 個人情報保護法 (415AC0000000057) (+16 more)

### Community 5 - "RAG Retrieval"
Cohesion: 0.14
Nodes (12): request(), _embed_query(), retrieve(), _voyage(), chat(), _FakePool, _FakeVoyage, _FakeVoyageResult (+4 more)

### Community 6 - "Contract Review Tooling"
Cohesion: 0.17
Nodes (16): Anthropic prompt caching (ephemeral), _build_rag_block (contract_review), REPORT_TOOL, _retrieval_query, review_contract, post_review, ReviewResponse, format_citations (+8 more)

### Community 7 - "Chunker Tests"
Cohesion: 0.22
Nodes (12): _body_text(), Chunk, chunk_law(), _count_tokens(), _has_header_ancestor(), Approximate token count. Uses tiktoken when available, falls back to len/2., Walk e-Gov 法令 XML and emit one Chunk per <Article>, splitting long ones.      Th, Concatenate non-empty text nodes under Article, skipping header elements. (+4 more)

### Community 8 - "Backend API (Hono)"
Cohesion: 0.23
Nodes (2): action(), reviewContract()

### Community 9 - "Contract Review Agent"
Cohesion: 0.36
Nodes (7): _build_rag_block(), _client(), 契約タイトル + 本文先頭 800 字を retrieval クエリにする。, _retrieval_query(), review_contract(), _system_prompt(), format_citations()

### Community 13 - "Pytest Fixtures"
Cohesion: 1.0
Nodes (1): Shared test setup: stub required envs before src.config is imported.

### Community 15 - "Chat Schemas"
Cohesion: 1.0
Nodes (2): ChatTurn, ChatRequest

### Community 26 - "Layout Component"
Cohesion: 1.0
Nodes (1): Layout root component

### Community 27 - "App Component"
Cohesion: 1.0
Nodes (1): App root

### Community 28 - "ErrorBoundary"
Cohesion: 1.0
Nodes (1): ErrorBoundary

### Community 29 - "Vite Frontend Config"
Cohesion: 1.0
Nodes (1): vite config (frontend)

### Community 30 - "React Router SSR Config"
Cohesion: 1.0
Nodes (1): react-router config (SSR on)

### Community 31 - "Fake Anthropic Stub"
Cohesion: 1.0
Nodes (1): _FakeAnthropic

### Community 32 - "ChatResponse Schema"
Cohesion: 1.0
Nodes (1): ChatResponse

### Community 33 - "ReviewRequest Schema"
Cohesion: 1.0
Nodes (1): ReviewRequest

## Knowledge Gaps
- **51 isolated node(s):** `Shared test setup: stub required envs before src.config is imported.`, `Approximate token count. Uses tiktoken when available, falls back to len/2.`, `Walk e-Gov 法令 XML and emit one Chunk per <Article>, splitting long ones.      Th`, `Concatenate non-empty text nodes under Article, skipping header elements.`, `e-Gov v2: GET /law_data/{law_id} → 法令本文 XML.` (+46 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Backend API (Hono)`** (13 nodes): `client.ts`, `schema.ts`, `env.ts`, `index.ts`, `chat.ts`, `contracts.ts`, `ai-client.ts`, `contracts.tsx`, `toMessage()`, `toThread()`, `action()`, `meta()`, `reviewContract()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Pytest Fixtures`** (2 nodes): `conftest.py`, `Shared test setup: stub required envs before src.config is imported.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Chat Schemas`** (2 nodes): `ChatTurn`, `ChatRequest`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Layout Component`** (1 nodes): `Layout root component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `App Component`** (1 nodes): `App root`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ErrorBoundary`** (1 nodes): `ErrorBoundary`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Vite Frontend Config`** (1 nodes): `vite config (frontend)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `React Router SSR Config`** (1 nodes): `react-router config (SSR on)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Fake Anthropic Stub`** (1 nodes): `_FakeAnthropic`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ChatResponse Schema`** (1 nodes): `ChatResponse`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ReviewRequest Schema`** (1 nodes): `ReviewRequest`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `retrieve()` connect `RAG Retrieval` to `Contract Review Agent`, `Legal Chat Agent`, `AI App Bootstrap & Ingest`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Why does `Citation` connect `Legal Chat Agent` to `RAG Retrieval`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Why does `reviewContract()` connect `Backend API (Hono)` to `RAG Retrieval`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `ChatTurn` (e.g. with `_FakeBlock` and `_FakeResponse`) actually correct?**
  _`ChatTurn` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `Citation` (e.g. with `_FakeBlock` and `_FakeResponse`) actually correct?**
  _`Citation` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `chunk_law()` (e.g. with `test_chunk_law_emits_one_chunk_per_article()` and `test_chunk_law_skips_articles_with_no_body()`) actually correct?**
  _`chunk_law()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `chatRouter (Hono)` (e.g. with `api.listThreads` and `api.createThread`) actually correct?**
  _`chatRouter (Hono)` has 4 INFERRED edges - model-reasoned connections that need verification._