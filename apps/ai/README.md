# apps/ai — 法務AI Agent (Python)

Anthropic Claude を呼び出して契約書レビューと法務相談を提供する FastAPI サービス。

## セットアップ

```bash
# uv が無い場合
curl -LsSf https://astral.sh/uv/install.sh | sh

# 依存解決
uv sync

# .env をルートに置いた状態で起動
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## エンドポイント

- `GET /health` — ヘルスチェック
- `POST /review` — 契約書レビュー (`{title, body}` → `{model, summary, risks[]}`)
- `POST /chat` — 法務相談 (`{messages: [{role, content}]}` → `{model, content}`)
- `POST /research` — ReAct ループ版の法務リサーチ (`{question, max_iterations?}` → `{model, content, iterations}`)。
  Claude が `search_laws` ツールを反復呼び出しして、必要に応じて検索クエリを改善しながら最終回答を作る。

## RAG (e-Gov 法令データ)

`/chat` と `/review` は Postgres + pgvector に蓄えた法令条文を Voyage `voyage-3` で
類似検索し、Claude のシステムブロック（uncached）に「## 参考法令」として注入する。
取り込みは手動 CLI:

```bash
uv run python -m src.ingest.egov --law-id 129AC0000000089            # 単発
uv run python -m src.ingest.egov --allowlist src/ingest/laws_allowlist.txt  # 一括
```

`RAG_ENABLED=false` を設定すると RAG 注入をスキップする。詳細はリポジトリ root の README.md を参照。

## reranker (オプトイン)

`.env` に `RERANK_ENABLED=true` を入れると、dense 検索の結果を Voyage `rerank-2` (cross-encoder)
で並べ直す。`RERANK_CANDIDATE_MULTIPLIER` (default 3) で over-fetch 倍率を調整。

## Eval

`evals/` に golden データセット + ランナー + LLM-as-judge スコアラーが入っている。
詳細は `evals/README.md`。

```bash
uv run python -m evals.run --agent legal_chat                 # full run
uv run python -m evals.run --agent research_agent --limit 3   # 3 件のみ
uv run python -m evals.run --agent legal_chat --skip-judge    # judge 省略
```
