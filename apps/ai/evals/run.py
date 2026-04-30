"""Eval harness for the legal AI agents.

Pipeline (一気通貫):

  1. dataset.jsonl から golden 質問を読み込む
  2. 各質問を agent (legal_chat or research_agent) に流し、
     trace (回答 / 引用 / トークン使用 / レイテンシ) を保存する
  3. trace を 2 軸でスコア:
       - 期待キーワードのヒット率 (heuristic)
       - LLM-as-judge による回答品質スコア (1-5)
  4. markdown レポートに集計を出す

実行例:

  uv run python -m evals.run --agent legal_chat                 # full run
  uv run python -m evals.run --agent research_agent --limit 3   # 3 件だけ
  uv run python -m evals.run --agent legal_chat --skip-judge    # LLM-as-judge を省略

出力先: apps/ai/evals/runs/<timestamp>/
  - traces.jsonl   : 各質問の生 trace
  - scores.jsonl   : スコアリング結果
  - report.md      : 人間用サマリ
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from src.agents.legal_chat import ChatTurn
from src.agents.legal_chat import reply as legal_chat_reply
from src.agents.research_agent import research as research_agent_run
from src.config import settings

EVAL_DIR = Path(__file__).resolve().parent
DATASET_PATH = EVAL_DIR / "dataset.jsonl"
RUNS_DIR = EVAL_DIR / "runs"


# ---------------------------------------------------------------------------
# 1. dataset
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    expected_keywords: list[str]
    must_cite: bool
    category: str


def load_dataset(path: Path = DATASET_PATH) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            cases.append(
                EvalCase(
                    id=row["id"],
                    question=row["question"],
                    expected_keywords=list(row.get("expected_keywords", [])),
                    must_cite=bool(row.get("must_cite", False)),
                    category=str(row.get("category", "")),
                )
            )
    return cases


# ---------------------------------------------------------------------------
# 2. runner
# ---------------------------------------------------------------------------


async def _run_legal_chat(question: str) -> dict[str, Any]:
    started = time.perf_counter()
    result = await legal_chat_reply([ChatTurn(role="user", content=question)])
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "model": result.get("model", ""),
        "content": result.get("content", ""),
        "latency_ms": latency_ms,
        "iterations": 1,
        "citations": [],
        "usage": {},
    }


async def _run_research_agent(question: str) -> dict[str, Any]:
    result = await research_agent_run(question)
    return {
        "model": result.get("model", ""),
        "content": result.get("content", ""),
        "latency_ms": result.get("latency_ms", 0),
        "iterations": result.get("iterations", 0),
        "citations": result.get("citations", []),
        "usage": result.get("usage", {}),
    }


AGENTS = {
    "legal_chat": _run_legal_chat,
    "research_agent": _run_research_agent,
}


async def run_traces(
    cases: list[EvalCase],
    agent: str,
    out_path: Path,
) -> list[dict[str, Any]]:
    runner = AGENTS[agent]
    traces: list[dict[str, Any]] = []
    for case in cases:
        print(f"  [{case.id}] {case.question[:40]}…")
        try:
            run = await runner(case.question)
            trace = {"case_id": case.id, "question": case.question, **run, "error": None}
        except Exception as exc:  # noqa: BLE001
            trace = {
                "case_id": case.id,
                "question": case.question,
                "model": "",
                "content": "",
                "latency_ms": 0,
                "iterations": 0,
                "citations": [],
                "usage": {},
                "error": f"{type(exc).__name__}: {exc}",
            }
        traces.append(trace)
    out_path.write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in traces) + "\n",
        encoding="utf-8",
    )
    return traces


# ---------------------------------------------------------------------------
# 3. scoring
# ---------------------------------------------------------------------------


def _score_keywords(content: str, expected: list[str]) -> float:
    if not expected:
        return 1.0
    hits = sum(1 for kw in expected if kw in content)
    return hits / len(expected)


JUDGE_PROMPT = (
    "あなたは法務領域の評価者です。以下の質問と回答を読み、回答の品質を 1〜5 で評価してください。\n"
    "評価基準:\n"
    "  5: 法的に正確で、根拠条文も適切に引用され、結論が明瞭\n"
    "  4: 概ね正確だが軽微な不備あり\n"
    "  3: 概略は合っているが重要な要素が欠けている\n"
    "  2: 部分的に誤り、または根拠が薄い\n"
    "  1: 重大な誤りを含む / 質問にほぼ答えていない\n"
    '出力は JSON のみで、形式は {"score": <int>, "reason": <str>}。'
)


@lru_cache(maxsize=1)
def _judge_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


async def _score_with_judge(question: str, content: str) -> dict[str, Any]:
    if not content.strip():
        return {"score": 1, "reason": "empty answer"}
    response = await _judge_client().messages.create(
        model=settings.anthropic_model,
        max_tokens=400,
        system=JUDGE_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"# 質問\n{question}\n\n# 回答\n{content}\n\n"
                    "上記の回答を評価し、JSON で出してください。"
                ),
            }
        ],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    try:
        # 単純化: 最初の { から最後の } までを取り出して JSON parse
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        pass
    return {"score": 0, "reason": f"could not parse judge output: {text[:200]}"}


async def score_traces(
    traces: list[dict[str, Any]],
    cases_by_id: dict[str, EvalCase],
    out_path: Path,
    skip_judge: bool,
) -> list[dict[str, Any]]:
    scores: list[dict[str, Any]] = []
    for trace in traces:
        case = cases_by_id[trace["case_id"]]
        keyword_score = _score_keywords(trace["content"], case.expected_keywords)
        if skip_judge or trace.get("error"):
            judge = {"score": None, "reason": "skipped"}
        else:
            judge = await _score_with_judge(case.question, trace["content"])
        scores.append(
            {
                "case_id": case.id,
                "category": case.category,
                "keyword_score": round(keyword_score, 3),
                "keyword_expected": case.expected_keywords,
                "judge_score": judge.get("score"),
                "judge_reason": judge.get("reason", ""),
                "latency_ms": trace.get("latency_ms", 0),
                "iterations": trace.get("iterations", 0),
                "error": trace.get("error"),
            }
        )
    out_path.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in scores) + "\n",
        encoding="utf-8",
    )
    return scores


# ---------------------------------------------------------------------------
# 4. report
# ---------------------------------------------------------------------------


def render_report(
    scores: list[dict[str, Any]],
    agent: str,
    out_path: Path,
) -> None:
    lines: list[str] = []
    lines.append(f"# Eval Report — {agent}")
    lines.append("")
    lines.append(f"- Run at: {datetime.now(UTC).isoformat()}")
    lines.append(f"- Cases: {len(scores)}")

    keyword_scores = [s["keyword_score"] for s in scores if s["error"] is None]
    judge_scores = [s["judge_score"] for s in scores if s.get("judge_score") is not None]
    latencies = [s["latency_ms"] for s in scores if s["error"] is None]
    errors = [s for s in scores if s.get("error")]

    if keyword_scores:
        lines.append(f"- Keyword hit rate (avg): {statistics.fmean(keyword_scores):.2%}")
    if judge_scores:
        lines.append(f"- Judge score (avg): {statistics.fmean(judge_scores):.2f} / 5")
    if latencies:
        lines.append(f"- Latency: p50={int(statistics.median(latencies))}ms max={max(latencies)}ms")
    lines.append(f"- Errors: {len(errors)}")
    lines.append("")
    lines.append("## Per-case")
    lines.append("")
    lines.append("| id | category | keyword | judge | latency | iters | note |")
    lines.append("|----|----------|---------|-------|---------|-------|------|")
    for s in scores:
        note = s["error"] if s["error"] else (s.get("judge_reason") or "")
        note = note.replace("\n", " ")[:60]
        judge = s["judge_score"] if s["judge_score"] is not None else "-"
        lines.append(
            f"| {s['case_id']} | {s['category']} | "
            f"{s['keyword_score']:.0%} | {judge} | "
            f"{s['latency_ms']}ms | {s['iterations']} | {note} |"
        )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(description="Eval harness")
    parser.add_argument(
        "--agent",
        choices=list(AGENTS),
        default="legal_chat",
        help="どの agent を評価するか",
    )
    parser.add_argument("--limit", type=int, default=0, help="先頭から N 件だけ実行 (0=全件)")
    parser.add_argument("--skip-judge", action="store_true", help="LLM-as-judge を省略")
    args = parser.parse_args()

    cases = load_dataset()
    if args.limit > 0:
        cases = cases[: args.limit]
    cases_by_id = {c.id: c for c in cases}

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS_DIR / f"{timestamp}-{args.agent}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] running {len(cases)} cases against {args.agent}…")
    traces = await run_traces(cases, args.agent, run_dir / "traces.jsonl")

    print(f"[2/3] scoring (skip_judge={args.skip_judge})…")
    scores = await score_traces(traces, cases_by_id, run_dir / "scores.jsonl", args.skip_judge)

    print("[3/3] writing report…")
    render_report(scores, args.agent, run_dir / "report.md")

    print(f"\n→ {run_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
