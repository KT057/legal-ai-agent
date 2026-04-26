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

| 確認項目 | 手順 |
| --- | --- |
| AI ヘルス | `curl http://localhost:8000/health` |
| Backend ヘルス | `curl http://localhost:3001/api/health` |
| 契約書レビュー | `/contracts` で NDA などを貼り付け → リスク指摘が返る |
| 法務相談チャット | `/chat` で新規スレッド作成 → 質問送信 → 回答が返る |

## スクリプト

| コマンド | 説明 |
| --- | --- |
| `pnpm dev` | frontend + backend を turbo で並列起動 |
| `pnpm dev:ai` | AI サービス (FastAPI) を起動 |
| `pnpm db:up` / `pnpm db:down` | PostgreSQL の起動・停止 |
| `pnpm db:generate` | drizzle スキーマからマイグレーション生成 |
| `pnpm db:migrate` | マイグレーション適用 |
| `pnpm lint` | Biome lint (TS のみ) |
| `pnpm typecheck` | 型チェック |

## 主要技術

| 領域 | 採用技術 | 補足 |
| --- | --- | --- |
| フロントエンド | React Router v7 | SSR デフォルト ON, Vite |
| バックエンド | Hono + Drizzle ORM | Node.js ランタイム, postgres-js |
| AI | Anthropic Claude (`claude-opus-4-7`) | tool use で構造化出力, prompt caching 有効 |
| RAG | e-Gov 法令API + Voyage `voyage-3` + pgvector | `/chat` と `/review` で参考法令を引用 |
| DB | PostgreSQL 16 + pgvector | docker compose で起動 |
| バリデーション | zod / pydantic | |
| Lint/Format | Biome (TS) / Ruff (Python) | |
| モノレポ | pnpm workspace + Turbo | |

## ディレクトリの役割

- `packages/shared-types` — `ContractReview` / `ChatMessage` 等の DTO。frontend/backend の両方で利用
- `apps/backend/src/services/ai-client.ts` — Python AI サービスへの薄いプロキシ
- `apps/ai/src/prompts/` — システムプロンプトを Markdown で外出し
- `apps/ai/src/agents/` — Claude を呼び出すエージェント本体
- `apps/ai/src/rag/` — クエリ埋め込み + pgvector 検索 + 引用フォーマット
- `apps/ai/src/ingest/` — e-Gov 法令API クライアント / 条チャンク分割 / Voyage embedder / 取り込み CLI

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

## トラブルシューティング

### `/api/chat/threads` が 500 を返す

PostgreSQL が起動していない、またはマイグレーション未適用が原因。`pnpm db:up` → pgvector 拡張有効化 → `pnpm db:generate && pnpm db:migrate` の順で実行。

### `/api/chat/threads/.../messages` が `{"error":"fetch failed"}` を返す

AI サービス（FastAPI, :8000）が起動していない。別ターミナルで `pnpm dev:ai` を立てる。Anthropic/Voyage の API キーがダミー（`sk-ant-xxxx...`）のままだと AI 側で失敗するので、`.env` の `ANTHROPIC_API_KEY` と `VOYAGE_API_KEY` を実キーに差し替える。RAG を切り分けたいときは `RAG_ENABLED=false`。

### Colima で `pnpm db:up` が permission denied で失敗する

Colima の sshfs マウント上では PostgreSQL の `chown` が拒否され、コンテナ起動に失敗する。本リポジトリの `docker/docker-compose.yml` は named volume (`postgres_data`) を使うのでこの問題は出ないが、bind mount に戻す場合は Colima を 9p / virtiofs マウントで再起動するか、Docker Desktop に切り替える必要がある。

## スコープ外（今は入れていない）

- 認証 / 認可（シングルユーザー想定）
- PDF/DOCX のアップロード（テキスト直貼りのみ）
- ストリーミング応答（SSE）
- 判例 / 官報の取り込み
- スケジューラ（cron / GitHub Actions / APScheduler）による定期更新
- 契約書ドラフト自動生成
- CI/CD・本番デプロイ
