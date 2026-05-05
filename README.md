# legal-ai-agent

法務業務（契約書レビュー・法務相談）を肩代わりする AI Agent。

## 構成

```
legal-ai-agent/ (pnpm workspace + Turbo)
├── apps/
│   ├── frontend/    React Router v7 (SSR, Vite)            :3000
│   ├── backend/     Hono + Drizzle ORM + PostgreSQL        :3001
│   └── ai/          FastAPI + Anthropic Claude (Python/uv) :8000
├── packages/
│   └── shared-types/    frontend ⇔ backend 共有 DTO
└── docker/
    └── docker-compose.yml    PostgreSQL 16 + pgvector
```

```
Frontend (React Router) ──REST──▶ Backend (Hono) ──REST──▶ AI (FastAPI + Claude)
                                       │
                                       ▼
                                   PostgreSQL
```

## 必要なもの

- Node.js >= 20.11
- pnpm >= 9
- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Docker (PostgreSQL 用)
- Anthropic API Key

## セットアップ

```bash
# 1. 環境変数
cp .env.example .env
# ANTHROPIC_API_KEY を必ず設定

# 2. 依存インストール
pnpm install
cd apps/ai && uv sync && cd ../..

# 3. PostgreSQL (pgvector) を起動
pnpm db:up

# 4. pgvector 拡張を有効化（初回のみ）
docker compose -f docker/docker-compose.yml exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  < apps/backend/src/db/setup-pgvector.sql

# 5. DB マイグレーション
pnpm db:generate    # 初回のみ
pnpm db:migrate

# 6. 法令データを取り込み（最新の e-Gov 法令データを RAG 用に投入）
cd apps/ai
uv run python -m src.ingest.egov --allowlist src/ingest/laws_allowlist.txt
cd ../..
```

## 起動

ターミナル A — AI サービス (Python):

```bash
pnpm dev:ai
# → http://localhost:8000
```

ターミナル B — frontend + backend:

```bash
pnpm dev
# frontend → http://localhost:3000
# backend  → http://localhost:3001
```

ブラウザで `http://localhost:3000` を開く。

## 動作確認

| 確認項目             | 手順                                                                                                                   |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| AI ヘルス            | `curl http://localhost:8000/health`                                                                                    |
| Backend ヘルス       | `curl http://localhost:3001/api/health`                                                                                |
| 契約書レビュー       | `/contracts` で NDA などを貼り付け or PDF アップロード → リスク指摘が返る                                              |
| 法務相談チャット     | `/chat` で新規スレッド作成 → 質問送信 → 回答が返る                                                                     |
| 法務リサーチ (ReAct) | `curl POST /api/research` または `/research` 画面で質問送信                                                            |
| NDA ドラフト生成     | `/draft` で engine (v1 / v2) を選んで新規セッション → 要件をヒアリング → 「ドラフトを生成」で draft → review → revised |

## スクリプト

| コマンド                      | 説明                                          |
| ----------------------------- | --------------------------------------------- |
| `pnpm dev`                    | frontend + backend を turbo で並列起動        |
| `pnpm dev:ai`                 | AI サービス (FastAPI) を起動                  |
| `pnpm db:up` / `pnpm db:down` | PostgreSQL の起動・停止                       |
| `pnpm db:generate`            | drizzle スキーマからマイグレーション生成      |
| `pnpm db:migrate`             | マイグレーション適用                          |
| `pnpm lint`                   | ESLint (TS のみ)                              |
| `pnpm format`                 | Prettier 整形                                 |
| `pnpm format:check`           | Prettier フォーマットチェック                 |
| `pnpm typecheck`              | 型チェック                                    |
| `pnpm eval:chat`              | legal_chat agent を golden データセットで評価 |
| `pnpm eval:research`          | research_agent (ReAct) を評価                 |
| `pnpm eval:draft`             | contract_draft v1 (直接 SDK 4 phase) を評価   |
| `pnpm eval:draft:v2`          | contract_draft v2 (LangGraph) を評価          |
| `pnpm langfuse:up`            | Langfuse (LLM observability) を起動           |
| `pnpm langfuse:down`          | Langfuse を停止                               |
| `pnpm langfuse:logs`          | langfuse-web / worker のログを追尾            |

## 主要技術

| 領域           | 採用技術                                     | 補足                                       |
| -------------- | -------------------------------------------- | ------------------------------------------ |
| フロントエンド | React Router v7                              | SSR デフォルト ON, Vite                    |
| バックエンド   | Hono + Drizzle ORM                           | Node.js ランタイム, postgres-js            |
| AI             | Anthropic Claude (`claude-opus-4-7`)         | tool use で構造化出力, prompt caching 有効 |
| RAG            | e-Gov 法令API + Voyage `voyage-3` + pgvector | `/chat` と `/review` で参考法令を引用      |
| DB             | PostgreSQL 16 + pgvector                     | docker compose で起動                      |
| バリデーション | zod / pydantic                               |                                            |
| Lint/Format    | ESLint + Prettier (TS) / Ruff (Python)       |                                            |
| モノレポ       | pnpm workspace + Turbo                       |                                            |

## ディレクトリの役割

- `packages/shared-types` — `ContractReview` / `ChatMessage` 等の DTO。frontend/backend の両方で利用
- `apps/backend/src/services/ai-client.ts` — Python AI サービスへの薄いプロキシ
- `apps/ai/src/prompts/` — システムプロンプトを Markdown で外出し
- `apps/ai/src/agents/` — Claude を呼び出すエージェント本体
- `apps/ai/src/rag/` — クエリ埋め込み + pgvector 検索 + 引用フォーマット
- `apps/ai/src/ingest/` — e-Gov 法令API クライアント / 条チャンク分割 / Voyage embedder / 取り込み CLI
- `apps/ai/evals/` — golden データセット + ランナー + LLM-as-judge スコアリング (回帰・改善計測用)

## RAG（法令引用）

`/chat` と `/review` の Claude 呼び出し前に、ユーザー質問または契約本文の先頭 800 字をクエリとして
`law_chunks` テーブル（pgvector + HNSW + cosine）から類似条文を top-k 件取得し、システムブロックに
「## 参考法令」として注入する。Claude は回答末尾に `[番号]` 形式の引用 ID を付与する。

- 取り込み元: e-Gov 法令API v2（`https://laws.e-gov.go.jp/api/2`）
- Embeddings: Voyage AI `voyage-3`（1024 dim, cosine）
- チャンク粒度: `<Article>` 単位（800 トークン超は文字幅 600 / overlap 80 で分割）
- 更新方式（v1）: 手動 CLI のみ。allowlist またはピンポイントの LawId を指定して再実行

```bash
# 単発
uv run python -m src.ingest.egov --law-id 129AC0000000089

# 複数
uv run python -m src.ingest.egov --law-ids 129AC0000000089,406AC0000000085

# allowlist 一括
uv run python -m src.ingest.egov --allowlist src/ingest/laws_allowlist.txt
```

`RAG_ENABLED=false` を設定すると RAG ブロックの注入をスキップする。
プロンプトキャッシュは静的システムプロンプトのみに適用され、RAG ブロックは別ブロックでキャッシュされない。

## エージェントの 4 形態

このリポジトリでは Claude Anthropic SDK / LangGraph を使ったエージェントを 4 つの典型パターンで実装している。
学習目的で「同じ問題に対する設計の違い」「単発生成 vs 反復 vs 多段ワークフロー vs declarative DAG」が
並べて読めるようにしている。

| 形態                          | 場所                                      | 動作                                                                                                                                                            | 強み                                                       | 弱み                                                                |
| ----------------------------- | ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------- |
| **RAG injection (1-shot)**    | `apps/ai/src/agents/legal_chat.py`        | クエリで 1 回 retrieve → 結果をシステムブロックに注入 → 1 回生成                                                                                                | 速い・トークン安い・キャッシュが効く                       | 最初の検索で外したらリカバリ不能                                    |
| **ReAct loop**                | `apps/ai/src/agents/research_agent.py`    | tool (`search_laws`) を Claude に渡し、`tool_use` → `tool_result` のラリーを `max_iterations` まで回し、収束した時点で最終回答                                  | クエリを反復で洗練できる・観察 → 行動の循環                | 遅い・トークンが嵩む・無限ループ防止が必要                          |
| **Multi-phase workflow (v1)** | `apps/ai/src/agents/contract_draft.py`    | hearing (tool_choice="any" で要件抽出) → draft → review (`report_review` tool で構造化リスク抽出) → revise の 4 phase を直接 SDK + Python の `await` で順次実行 | 制御フローが Python に閉じる・依存最小・明示的で読みやすい | 条件分岐 / 循環を増やすと if/while で散らかりやすい                 |
| **LangGraph StateGraph (v2)** | `apps/ai/src/agents/contract_draft_v2.py` | 同じ 4 phase ワークフローを LangGraph の StateGraph で declarative に組み、revise 後に高/中リスクが多ければ条件付きで再 revise を 1 周回す                      | 条件分岐・循環・チェックポイントを宣言的に書ける           | 依存追加 (`langgraph` / `langchain-anthropic`) と抽象層の学習コスト |

`POST /research` で ReAct 版を直接叩ける（`{"question": "...", "max_iterations": 5}`）。
`POST /draft/hearing` / `POST /draft/generate` で v1 (直接 SDK) を、
`POST /draft-v2/hearing` / `POST /draft-v2/generate` で v2 (LangGraph) を叩ける。
`/draft` 画面の「engine」ラジオで v1 / v2 を切り替えるとサイドバーに `[v1]` / `[v2 LG]` バッジが付く。

### NDA ドラフト生成 (multi-phase agentic workflow)

```
Frontend /draft (RR v7)
   ├─ POST /api/drafts/sessions               (新規セッション)
   ├─ GET  /api/drafts/sessions               (一覧)
   ├─ GET  /api/drafts/sessions/:id           (詳細 + 全 turns)
   ├─ POST /api/drafts/sessions/:id/messages  (Hearing 1 ターン分追加)
   └─ POST /api/drafts/sessions/:id/generate  (Draft → Self-review → Revise を一気に実行)
                                  │
                                  ▼
Backend (Hono)  → ai-client.ts → FastAPI (apps/ai)
                                  ├─ POST /draft/hearing   (1 ターン進める; 要件抽出 tool_use)
                                  └─ POST /draft/generate  (draft → review → revise を直列実行)
```

DB は `draft_sessions` (1 行 = 1 NDA セッション) と
`draft_turns` (1 行 = hearing 発話 / generate phase の成果物) の dual-table 構成。

**ヒアリング**で集める必須 6 項目:

- `disclosingParty` / `receivingParty` (両当事者の正式社名)
- `purpose` (開示目的)
- `confidentialInfoScope` (秘密情報の範囲)
- `termMonths` (有効期間, 月単位)
- `governingLaw` (準拠法; default = 日本法)

**スモーク (curl)**:

```bash
# 1. ヒアリング (1 ターン)
curl -X POST http://localhost:8000/draft/hearing \
  -H 'Content-Type: application/json' \
  -d '{"history": [], "userMessage": "AIスタートアップA社と事業会社B社が、製品の共同検証のためのNDAを作りたい"}'
# → tool_use (update_requirements + ask_user) が返り、現状要件 + 次の質問が出る

# 2. 確定要件で一発生成 (3 phase)
curl -X POST http://localhost:8000/draft/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "requirements": {
      "disclosingParty": "株式会社AIスタートアップ",
      "receivingParty": "株式会社事業会社",
      "purpose": "新製品の共同検証",
      "confidentialInfoScope": "技術情報および顧客情報",
      "termMonths": 12,
      "governingLaw": "日本法"
    }
  }'
# → draftV1 / risks / reviewSummary / finalDraft が返る (latency 90〜180s)
```

### v1 vs v2: 直接 SDK と LangGraph の書き比べ

同じワークフロー (hearing → draft → review → revise) を 2 通りで実装し、
**コード読み比べと eval スコア比較** ができるようにしてある。

| 観点                 | v1 (`contract_draft.py`)                                                        | v2 (`contract_draft_v2.py`)                                                                                                |
| -------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| 依存                 | `anthropic` のみ                                                                | `anthropic` + `langgraph` + `langchain-anthropic`                                                                          |
| LLM クライアント     | `AsyncAnthropic` を `_client()` でシングルトン                                  | `ChatAnthropic` (LangChain ラッパ) を `_llm()` でシングルトン                                                              |
| 制御フローの書き方   | `await draft → await review → await revise` を関数内で直書き                    | `StateGraph` に `add_node` / `add_edge` / `add_conditional_edges` を declarative に並べて `compile().ainvoke()`            |
| state の持ち方       | 関数引数 + ローカル変数 + 戻り値 dict                                           | `TypedDict` (`HearingState`, `GenerateState`) を node 間で merge                                                           |
| tool 呼び出し        | `messages.create(..., tools=..., tool_choice=...)` を直接書く                   | `llm.bind_tools(TOOLS, tool_choice=...)` で runnable を作る → `ainvoke()`、結果は `AIMessage.tool_calls[i]["args"]` に入る |
| 強制ツール呼び出し   | `tool_choice={"type": "any"}` / `{"type": "tool", "name": "..."}`               | 同形式を文字列 `"any"` または同じ dict で渡す (LangChain が adapter)                                                       |
| プロンプトキャッシュ | `system=[{"type":"text","text":...,"cache_control":{"type":"ephemeral"}}, ...]` | `SystemMessage(content=[{...},{...}])` の各要素に `cache_control` を入れる (adapter が透過)                                |
| Langfuse 計装        | `@observe` + `traced_messages_create` で 1 generation/呼び出し                  | `@observe` のみ (LangChain native の callback は今回入れていない)                                                          |
| 条件分岐 / 循環      | `if`/`while` で書く必要がある                                                   | `add_conditional_edges("revise", should_loop, {"revise": "revise", END: END})` で 1 行                                     |
| 学習価値             | Anthropic SDK の挙動が透けて見える・最小依存で読みやすい                        | declarative DAG + state machine の感覚を実コードで体験できる                                                               |

**v2 で差別化した条件ループ** (`should_loop`):

- `revise_count >= 2` で必ず `END` (暴走防止)
- `risks` に high が 1 件以上 OR medium が 5 件以上あれば `revise` に戻る
- そうでなければ `END`

これにより、品質懸念が大きい時だけ追加で 1 周回す挙動を **5 行ほどの判定関数 +
1 行の `add_conditional_edges`** で表現できる (v1 で同じことをすると、generate 関数の
中に `while` ループとガード条件を埋め込む必要がある)。

**eval で公平比較**:

```bash
# 同じ golden case (draft-001..004) を v1/v2 双方で走らせる
pnpm eval:draft         --run-name baseline-v1
pnpm eval:draft:v2      --run-name baseline-v2
# Langfuse UI で keyword_hit_rate / judge_score / latency_ms を 2 run 並列比較
```

## reranker (オプトイン)

`apps/ai/src/rag/retriever.py` は dense 検索の上に Voyage `rerank-2` を載せられる。
`.env` に `RERANK_ENABLED=true` を設定すると、

1. dense で `rag_top_k * rerank_candidate_multiplier` 件を over-fetch
2. rerank-2 (cross-encoder) で再スコアリング
3. 上位 `rag_top_k` 件を返す（`Citation.score` は rerank score に置換される）

という挙動になる。

精度の効きを **eval で定量比較** するのが推奨ワークフロー:

```bash
# rerank off
RERANK_ENABLED=false uv run python -m evals.run --agent legal_chat
# rerank on
RERANK_ENABLED=true  uv run python -m evals.run --agent legal_chat
# それぞれの apps/ai/evals/runs/<...>/report.md を比較
```

## Eval (回答品質の定量評価)

prompt / モデル / RAG パラメータ / reranker の効果を回帰検知 + 改善検証できるよう、
`apps/ai/evals/` に harness を入れている。**Langfuse 有効時は Dataset Run として
自動的に UI で比較可能**、無効時はローカル JSONL/Markdown にフォールバックする 2 モード構成。

### モード自動切替

| 条件                                           | モード   | データソース          | スコア出力先                                                  |
| ---------------------------------------------- | -------- | --------------------- | ------------------------------------------------------------- |
| `LANGFUSE_TRACING_ENABLED=true` + キー設定済み | Langfuse | Langfuse Dataset      | Langfuse Scores (UI)                                          |
| 上記以外                                       | Local    | `evals/dataset.jsonl` | `evals/runs/<ts>-<agent>/{traces,scores}.jsonl` + `report.md` |

### Langfuse モード (推奨)

```bash
# 1. golden ケースを Langfuse Dataset に同期 (一度だけ。dataset.jsonl を SSOT)
cd apps/ai
uv run python -m evals.sync_dataset --name legal-ai-agent-eval

# 2. eval 実行 (各 case を Dataset Run として記録、スコアは UI に push)
uv run python -m evals.run --agent legal_chat
uv run python -m evals.run --agent legal_chat --run-name "before-prompt-fix"

# 3. UI で結果を確認 (Datasets → legal-ai-agent-eval → Runs)
open http://localhost:3030/project/legal-ai-agent-project/datasets
```

UI 上では各 run で `keyword_hit_rate` / `judge_score` / `forbidden_hits` / `latency_ms`
が並び、prompt 改修前後を 1 画面で比較できる。

### Local モード (Langfuse 無効時のフォールバック)

```bash
pnpm eval:chat                                                      # 全件
cd apps/ai && uv run python -m evals.run --agent legal_chat --limit 3 --skip-judge
pnpm eval:research                                                  # ReAct 版
uv run python -m evals.run --agent legal_chat --source jsonl        # 強制 Local
```

各実行で `apps/ai/evals/runs/<timestamp>-<agent>/report.md` が生成される（`.gitignore` 済み）。
スコア軸は **(1) keyword hit rate (heuristic)** と **(2) LLM-as-judge 1〜5** の 2 軸。

## Langfuse (LLM observability, self-hosted)

`apps/ai` は Anthropic SDK 直叩きで実装されているため、トレース・トークン使用量・
レイテンシ・キャッシュヒット率の可視化に Langfuse v3 を **セルフホスト** で利用する
（法務文書を扱う性質上、SaaS にプロンプト本文を流さない方針）。

### 起動

```bash
# 1. .env の Langfuse 関連項目をセット
#    - LANGFUSE_NEXTAUTH_SECRET / SALT / ENCRYPTION_KEY を openssl rand で生成
#    - LANGFUSE_INIT_* (org/project/user/keys) を設定 → 初回起動で自動作成される
#    - LANGFUSE_PUBLIC_KEY / SECRET_KEY / PROJECT_ID を init と同じ値で揃える
#    - LANGFUSE_INIT_USER_EMAIL は実在風 (foo@example.com) でないと Zod 検証で落ちる

# 2. Langfuse スタックを起動 (postgres + clickhouse + redis + minio + web + worker)
pnpm langfuse:up

# 3. ログイン
#    http://localhost:3030 → admin@example.com / password123 (LANGFUSE_INIT_USER_*)
#    → ダッシュボードのプロジェクトを開く: /project/legal-ai-agent-project/...
#    → LANGFUSE_TRACING_ENABLED=true を確認

# 4. 依存関係を更新 (langfuse パッケージが追加されている)
cd apps/ai && uv sync && cd ../..

# 5. AI サービスを再起動
pnpm dev:ai
```

ログイン後の主要 URL:

- Traces: `http://localhost:3030/project/legal-ai-agent-project/traces`
- Datasets: `http://localhost:3030/project/legal-ai-agent-project/datasets`
- Generations: `http://localhost:3030/project/legal-ai-agent-project/generations`

`LANGFUSE_TRACING_ENABLED=false` または API キーが空の状態だと計装は完全に no-op
になり、Langfuse が起動していなくても本体は通常通り動作する（フェールセーフ設計）。

### 観測対象

| trace ルート          | 計装ファイル                                                              |
| --------------------- | ------------------------------------------------------------------------- |
| `legal_chat`          | `apps/ai/src/agents/legal_chat.py`                                        |
| `research_agent`      | `apps/ai/src/agents/research_agent.py`(ReAct iteration ごとに generation) |
| `contract_review`     | `apps/ai/src/agents/contract_review.py`                                   |
| `eval.legal_chat`     | `apps/ai/evals/run.py`                                                    |
| `eval.research_agent` | 同上                                                                      |

子 span として `rag.retrieve` / `rag.embed_query` / `rag.rerank` が記録される。
Anthropic レスポンスの `cache_creation_input_tokens` / `cache_read_input_tokens` も
`usage_details` に分解して保存されるので、UI 上でキャッシュヒット率が可視化される。

### eval 連携 (Level 3: 完全移行)

`evals/dataset.jsonl` を Langfuse Dataset に同期、各 eval 実行を Dataset Run として
UI 上で比較可能。詳細は上記「Eval (回答品質の定量評価)」セクション参照。

```bash
cd apps/ai
uv run python -m evals.sync_dataset --name legal-ai-agent-eval
uv run python -m evals.run --agent legal_chat --run-name "experiment-A"
# → http://localhost:3030/project/legal-ai-agent-project/datasets/legal-ai-agent-eval
```

### 注意

- Langfuse 用 PostgreSQL は **アプリの pgvector DB と別コンテナ** に分離（ポートも 5433）。
  ホスト直接接続が必要なケースは少ないが、観測 DB が肥大化してもアプリ側に影響しない。
- ClickHouse の初回起動は 30 秒前後かかる（healthcheck の `start_period: 60s` で吸収）。
- 本番運用では `.env` の `LANGFUSE_*_PASSWORD` / `LANGFUSE_NEXTAUTH_SECRET` /
  `LANGFUSE_SALT` / `LANGFUSE_ENCRYPTION_KEY` を必ずランダム値に差し替える。

## トラブルシューティング

### `/api/chat/threads` が 500 を返す

PostgreSQL が起動していない、またはマイグレーション未適用が原因。`pnpm db:up` → pgvector 拡張有効化 → `pnpm db:generate && pnpm db:migrate` の順で実行。

### `/api/chat/threads/.../messages` が `{"error":"fetch failed"}` を返す

AI サービス（FastAPI, :8000）が起動していない。別ターミナルで `pnpm dev:ai` を立てる。Anthropic/Voyage の API キーがダミー（`sk-ant-xxxx...`）のままだと AI 側で失敗するので、`.env` の `ANTHROPIC_API_KEY` と `VOYAGE_API_KEY` を実キーに差し替える。RAG を切り分けたいときは `RAG_ENABLED=false`。

### Colima で `pnpm db:up` が permission denied で失敗する

Colima の sshfs マウント上では PostgreSQL の `chown` が拒否され、コンテナ起動に失敗する。本リポジトリの `docker/docker-compose.yml` は named volume (`postgres_data`) を使うのでこの問題は出ないが、bind mount に戻す場合は Colima を 9p / virtiofs マウントで再起動するか、Docker Desktop に切り替える必要がある。

## スコープ外（今は入れていない）

- 認証 / 認可（シングルユーザー想定）
- DOCX のアップロード（PDF はサポート、それ以外はテキスト直貼りのみ）
- スキャン PDF / OCR（テキスト埋め込みのある PDF のみ対応）
- ストリーミング応答（SSE）
- 判例 / 官報の取り込み
- スケジューラ（cron / GitHub Actions / APScheduler）による定期更新
- 契約書ドラフト自動生成 (NDA のみ実装済み。契約種別の追加は未対応)
- DOCX 出力 / Word ファイル生成 (NDA ドラフトは Markdown 表示のみ)
- CI/CD・本番デプロイ

## 次の練習問題（AI エージェント開発をマスターしたい人向け）

このリポジトリで意図的に "薄く" 残してある領域。順に手を入れると agent 開発の
要点が一通り通る。

1. **ストリーミング応答 (SSE)** — `legal_chat` を `client.messages.stream()` 化し、
   `/api/chat/.../messages` を SSE で返す。フロントは `EventSource` で逐次描画。
   "ユーザー体感の改善は機能追加よりレイテンシ" を実感する練習。
2. **会話メモリ要約** — チャットスレッドが長くなったら過去ターンを要約して
   詰める仕組み。"context window vs cost" のトレードオフを学ぶ。
3. **ガードレール** — 入力 (prompt injection 検出 / PII redaction) と出力
   (法令名のハルシネーション検出 / 必須引用チェック) の 2 段階。`evals/` に
   ガードレール用テストケースを足して回帰させる。
4. **Eval の citation チェック** — `evals/run.py` の scorer に「引用 ID が
   実在する条文に一致するか」を加える (`research_agent` の `citations` を活用)。
5. **Hybrid 検索 (BM25 + dense)** — `tsvector` を `law_chunks` に追加し、
   PostgreSQL の `ts_rank` と pgvector のスコアを正規化して合算する。
6. **MCP 化** — `search_laws` ツールを MCP サーバとして切り出し、Claude Desktop
   / 他のクライアントから直接使えるようにする。
