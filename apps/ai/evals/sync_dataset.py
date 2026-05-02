"""``evals/dataset.jsonl`` を Langfuse Dataset として upsert する CLI。

このファイルが扱う AI 概念：

* **Dataset versioning** — golden 質問群を Langfuse の Dataset として登録すると、
  ``run`` (= eval 実行 1 回) を Dataset に紐づけて UI 上で版管理できる。
  「prompt 改修前 vs 改修後」のスコア差分が並べて見られる。
* **idempotent upsert** — 同じ ID で再登録すると Langfuse 側は既存アイテムを
  上書きするため、JSONL の差分追加は再実行で自動反映される。
* **JSONL を SSOT に保つ** — Langfuse UI から直接編集すると JSONL とズレるので、
  本リポジトリでは「JSONL が SSOT、Langfuse は読み専用ミラー」という運用にする。

実行例:

  uv run python -m evals.sync_dataset
  uv run python -m evals.sync_dataset --name legal_chat_eval
"""

from __future__ import annotations

import argparse
import sys

from src.config import settings
from src.observability import flush_langfuse, get_langfuse, tracing_enabled

from .run import load_dataset


def sync(name: str, description: str) -> int:
    """JSONL の各ケースを Langfuse Dataset アイテムとして upsert する。"""
    if not tracing_enabled():
        print(
            "Langfuse tracing is disabled. Set LANGFUSE_TRACING_ENABLED=true and"
            " LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY in .env first.",
            file=sys.stderr,
        )
        return 1
    client = get_langfuse()
    if client is None:
        print("Failed to initialize Langfuse client; check credentials.", file=sys.stderr)
        return 1

    cases = load_dataset()
    print(f"Loaded {len(cases)} cases from dataset.jsonl")

    # Dataset 自体を idempotent に作成（既存ならそのまま）。
    try:
        client.create_dataset(name=name, description=description)
    except Exception as exc:  # noqa: BLE001
        # 既存 Dataset の場合は API がエラーを返すことがあるが、無視して続行。
        print(f"  (note) create_dataset returned: {exc}")

    for case in cases:
        try:
            client.create_dataset_item(
                dataset_name=name,
                # id を JSONL 側の case.id にして idempotent にする。
                id=case.id,
                input={"question": case.question},
                expected_output={
                    "expected_keywords": case.expected_keywords,
                    "forbidden_keywords": case.forbidden_keywords,
                    "must_cite": case.must_cite,
                    "must_refuse": case.must_refuse,
                },
                metadata={"category": case.category},
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  [{case.id}] failed: {exc}", file=sys.stderr)
            continue
        print(f"  [{case.id}] synced")

    flush_langfuse()
    if settings.langfuse_project_id:
        url = f"{settings.langfuse_host}/project/{settings.langfuse_project_id}/datasets/{name}"
    else:
        url = f"{settings.langfuse_host} (LANGFUSE_PROJECT_ID 未設定: ログイン後に遷移)"
    print(f"\nDone. View at: {url}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync evals/dataset.jsonl to Langfuse Datasets")
    parser.add_argument("--name", default="legal-ai-agent-eval", help="Langfuse dataset 名")
    parser.add_argument(
        "--description",
        default="Auto-synced from apps/ai/evals/dataset.jsonl",
        help="Dataset の説明",
    )
    args = parser.parse_args()
    return sync(args.name, args.description)


if __name__ == "__main__":
    raise SystemExit(main())
