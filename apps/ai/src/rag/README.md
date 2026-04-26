# RAG module

`apps/ai` から Postgres + pgvector に対して直接 SELECT/INSERT を行うモジュール。

**Schema は `apps/backend` (Drizzle) が Single Source of Truth。**
このモジュールから `CREATE TABLE` / `ALTER TABLE` などの DDL を発行しないこと。
スキーマ変更は必ず `apps/backend/src/db/schema.ts` を更新し、`pnpm db:generate && pnpm db:migrate` で適用する。
