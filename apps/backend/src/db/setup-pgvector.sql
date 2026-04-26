-- One-shot bootstrap: enable pgvector before running `pnpm db:migrate`.
-- Apply this once on a fresh database. After this, drizzle-kit handles
-- all schema changes (including the `vector(1024)` column and HNSW index
-- defined on `lawChunks` in schema.ts).
--
-- Usage:
--   docker compose -f docker/docker-compose.yml exec -T postgres \
--     psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
--     < apps/backend/src/db/setup-pgvector.sql

CREATE EXTENSION IF NOT EXISTS vector;
