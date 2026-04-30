"""Eval harness for the legal AI agents.

このファイルが扱う AI 概念：

* **Eval（評価ハーネス）の意義** — プロンプト・モデル・RAG パラメータ・
  reranker の効果は「直感」では分からない。同じ golden 質問群に対して
  自動でスコアを出せる仕組みを置くと、変更が改善か後退かを **数値で** 比較できる。
* **2 軸スコア** — RAG 系の評価ではよく使われる組み合わせ。
  * **keyword hit rate**: 期待キーワードの出現率（heuristic、コスト 0、再現性高）
  * **LLM-as-judge**: もう 1 つの Claude に「この回答を 1〜5 で採点せよ」と頼む
    （高精度だが API コスト + ばらつき）
* **golden dataset (JSONL)** — 各行が 1 ケース：``{id, question,
  expected_keywords, must_cite, category}``。コミット履歴で改善を追跡できる
  ようテキストで持つ。
* **per-case エラー隔離** — 1 件失敗で run 全体を落とさない。trace に
  ``error`` フィールドを残し、レポートで失敗件数を可視化する。
* **trace の標準化** — agent ごとに戻り値構造が違っても、上位レイヤーが
  同じスキーマで読めるよう ``model / content / latency_ms / iterations /
  citations / usage / error`` に揃える。

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
    """1 件の golden ケース。

    Fields:
        id: ケースの一意 ID（レポート表示と差分追跡に使う）
        question: ユーザー発話の想定文
        expected_keywords: 回答に出てきてほしい単語のリスト
            （ヒット率で heuristic スコアを計算）
        must_cite: ``[番号]`` 形式の引用が必須かどうか（将来の citation チェック用）
        category: 法令カテゴリのタグ。失敗パターンの傾向分析に使う
    """

    id: str
    question: str
    expected_keywords: list[str]
    must_cite: bool
    category: str


def load_dataset(path: Path = DATASET_PATH) -> list[EvalCase]:
    """JSONL を 1 行 1 ケースで読み込む。

    JSONL を選んでいるのは、追加・差分・PR レビューがしやすいため。
    1 ケース 1 行なので git diff で「追加されたケース」「変更されたケース」が
    明瞭に見える。
    """
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
# 各 agent の戻り値スキーマを「標準化された trace dict」に揃える層。
# 上位の scoring / report はこの形さえ知っていれば動く。


async def _run_legal_chat(question: str) -> dict[str, Any]:
    """legal_chat (1-shot) を実行して標準 trace 形式に詰める。

    legal_chat は ``iterations`` の概念がないので 1 固定、``citations`` も
    呼び出し側に返さない設計のため空配列。レイテンシだけはここで計測する。
    """
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
    """research_agent (ReAct) を実行して標準 trace 形式に詰める。

    ReAct 版はエージェント側で latency / iterations / citations / usage を
    返してくれるのでそのまま転記する。
    """
    result = await research_agent_run(question)
    return {
        "model": result.get("model", ""),
        "content": result.get("content", ""),
        "latency_ms": result.get("latency_ms", 0),
        "iterations": result.get("iterations", 0),
        "citations": result.get("citations", []),
        "usage": result.get("usage", {}),
    }


# CLI で ``--agent`` に渡す名前 → runner 関数のマッピング。
AGENTS = {
    "legal_chat": _run_legal_chat,
    "research_agent": _run_research_agent,
}


async def run_traces(
    cases: list[EvalCase],
    agent: str,
    out_path: Path,
) -> list[dict[str, Any]]:
    """全ケースを順に実行し、trace を JSONL ファイルに書き出す。

    ポイント:
    - 例外は **ケース単位で握りつぶす**：1 件失敗で残りを止めない
      （error フィールドに型名 + メッセージを残す）
    - 1 行 1 trace の JSONL で書く（後段で再読込しやすく、grep しやすい）
    - 進捗は質問先頭 40 字を print（人間がモニターするときの最低限）
    """
    runner = AGENTS[agent]
    traces: list[dict[str, Any]] = []
    for case in cases:
        print(f"  [{case.id}] {case.question[:40]}…")
        try:
            run = await runner(case.question)
            trace = {"case_id": case.id, "question": case.question, **run, "error": None}
        except Exception as exc:  # noqa: BLE001
            # 失敗したケースも trace に残す（あとで再現したい時のメタデータとして必要）。
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
    """期待キーワードのヒット率（0.0〜1.0）。空リストなら満点扱い。

    超単純な substring マッチ。日本語は形態素解析しないと厳密に取れないが、
    法令名や条番号のような固有表現はそのまま含まれることが多いので
    実用上は十分な heuristic として機能する。
    """
    if not expected:
        return 1.0
    hits = sum(1 for kw in expected if kw in content)
    return hits / len(expected)


# LLM-as-judge の評価基準プロンプト。
# 各スコアの定義を明文化することで、judge 同士の一貫性とランダム性低減を狙う。
# JSON 出力を強制する文も入れている（後段の正規表現的パースで失敗しないように）。
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
    """評価用の Anthropic クライアント（agents 側と分けることで負荷を可視化）。"""
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


async def _score_with_judge(question: str, content: str) -> dict[str, Any]:
    """LLM-as-judge で 1 ケースを採点する。

    実装上の注意:
    - 空回答は API を呼ばずに即 score=1 を返す（コスト節約 + 妥当な下限）
    - judge は output に余計な前置きを付けることがあるので、
      ``{...}`` の最初〜最後を抜き出す **ゆるい JSON 抽出** で対応
    - パース失敗は score=0 + 原文（先頭 200 字）を reason に残し、
      レポート上で「judge が破綻した」ことが分かるようにする

    本番運用では `tool_choice` で構造化させた方が堅いが、シンプルさを優先している。
    """
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
        # （マークダウンの ```json``` フェンスや前置きを許容する保険）
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
    """各 trace を 2 軸（keyword + judge）で採点して JSONL に書き出す。

    ``skip_judge=True`` または trace に error がある場合は judge を呼ばない。
    CI で API コストを節約したい時に便利。
    """
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
    """スコアを Markdown レポート (report.md) として書き出す。

    集計内容:
    - keyword hit rate の平均（heuristic 軸）
    - judge score の平均（LLM 評価軸）
    - レイテンシ p50 / max（性能軸）
    - エラー件数（信頼性軸）
    - per-case テーブル（深掘り用）

    ``runs/<timestamp>-<agent>/report.md`` に書かれるので、
    git log を見るより実行日時順にディレクトリで比較できる。
    """
    lines: list[str] = []
    lines.append(f"# Eval Report — {agent}")
    lines.append("")
    lines.append(f"- Run at: {datetime.now(UTC).isoformat()}")
    lines.append(f"- Cases: {len(scores)}")

    # error が入っているケースは集計から除外（成功ケースのみで平均する）。
    keyword_scores = [s["keyword_score"] for s in scores if s["error"] is None]
    judge_scores = [s["judge_score"] for s in scores if s.get("judge_score") is not None]
    latencies = [s["latency_ms"] for s in scores if s["error"] is None]
    errors = [s for s in scores if s.get("error")]

    if keyword_scores:
        lines.append(f"- Keyword hit rate (avg): {statistics.fmean(keyword_scores):.2%}")
    if judge_scores:
        lines.append(f"- Judge score (avg): {statistics.fmean(judge_scores):.2f} / 5")
    if latencies:
        # p50 = median。max は外れ値（タイムアウト寸前など）の検知用。
        lines.append(f"- Latency: p50={int(statistics.median(latencies))}ms max={max(latencies)}ms")
    lines.append(f"- Errors: {len(errors)}")
    lines.append("")
    lines.append("## Per-case")
    lines.append("")
    lines.append("| id | category | keyword | judge | latency | iters | note |")
    lines.append("|----|----------|---------|-------|---------|-------|------|")
    for s in scores:
        # note 列はエラー優先で出し、なければ judge の reason を 60 字に切る。
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

    # タイムスタンプ付きディレクトリに成果物を書く。複数 run の比較がしやすい。
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
