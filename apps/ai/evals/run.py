"""Eval harness for the legal AI agents.

このファイルが扱う AI 概念：

* **Eval（評価ハーネス）の意義** — プロンプト・モデル・RAG パラメータ・
  reranker の効果は「直感」では分からない。同じ golden 質問群に対して
  自動でスコアを出せる仕組みを置くと、変更が改善か後退かを **数値で** 比較できる。
* **2 軸スコア** — RAG 系の評価ではよく使われる組み合わせ。
  * **keyword hit rate**: 期待キーワードの出現率（heuristic、コスト 0、再現性高）
  * **LLM-as-judge**: もう 1 つの Claude に「この回答を 1〜5 で採点せよ」と頼む
    （高精度だが API コスト + ばらつき）
* **golden dataset の二重化** — JSONL (リポジトリにコミットして diff 追跡) と
  Langfuse Dataset (UI から増減/比較) の両方をサポート。Langfuse 有効時は
  Langfuse 側を SSOT として読み、scores も Langfuse にプッシュする。
* **per-case エラー隔離** — 1 件失敗で run 全体を落とさない。
* **Dataset Run** — Langfuse モードでは ``item.observe(run_name)`` で各 trace を
  Dataset Run として記録し、UI 上で「prompt 改修前 vs 後」を並べて比較できる。

Pipeline (Langfuse モード = 既定):

  1. Langfuse Dataset から golden ケースを読み込む (``--source langfuse``)
  2. 各ケースを ``item.observe(run_name=...)`` の中で agent に流し、
     trace を Langfuse に Dataset Run として記録
  3. keyword hit rate / forbidden_hits / judge_score を ``langfuse.score()`` で送信
  4. 結果は Langfuse UI ({LANGFUSE_HOST}/datasets) で確認

Pipeline (Local モード = Langfuse 無効時のフォールバック):

  1. dataset.jsonl から golden 質問を読み込む
  2. 各質問を agent に流し、trace を JSONL に保存
  3. trace を 2 軸でスコアし、scores.jsonl に保存
  4. markdown レポートに集計を出す

実行例:

  uv run python -m evals.run --agent legal_chat                 # full run (auto)
  uv run python -m evals.run --agent legal_chat --source jsonl  # 強制 Local モード
  uv run python -m evals.run --agent research_agent --limit 3
  uv run python -m evals.run --agent legal_chat --skip-judge

出力先 (Local モードのみ): apps/ai/evals/runs/<timestamp>/
  - traces.jsonl / scores.jsonl / report.md
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
from src.observability import (
    flush_langfuse,
    get_langfuse,
    observe,
    traced_messages_create,
    tracing_enabled,
)

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
        forbidden_keywords: 回答に **出てきてはならない** 単語のリスト。
            ハルシネーションの検出用：架空の条番号や捏造された判例名など、
            「もし出たら即失格」の文字列を入れる。1 つでもヒットすれば違反扱い。
        must_cite: ``[番号]`` 形式の引用が必須かどうか（将来の citation チェック用）
        must_refuse: 「分からない」と拒否すべき質問かどうか。
            ``True`` の場合、judge は「拒否できたか / 捏造したか」軸で採点する。
        category: 法令カテゴリのタグ。失敗パターンの傾向分析に使う
    """

    id: str
    question: str
    expected_keywords: list[str]
    forbidden_keywords: list[str]
    must_cite: bool
    must_refuse: bool
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
                    # forbidden_keywords / must_refuse は後付けフィールドなので
                    # 既存のデータセット行を壊さないように get でデフォルト供給する。
                    forbidden_keywords=list(row.get("forbidden_keywords", [])),
                    must_cite=bool(row.get("must_cite", False)),
                    must_refuse=bool(row.get("must_refuse", False)),
                    category=str(row.get("category", "")),
                )
            )
    return cases


def load_dataset_from_langfuse(name: str) -> list[EvalCase]:
    """Langfuse Dataset から golden ケースを引いて ``EvalCase`` に詰める。

    JSONL 版と同じ形に揃えることで、上位の runner / scorer から見ると
    データソースが透過になる。``input`` / ``expected_output`` / ``metadata`` の
    キー命名は ``evals/sync_dataset.py`` と整合させている。
    """
    client = get_langfuse()
    if client is None:
        raise RuntimeError(
            "Langfuse client is not available. "
            "Set LANGFUSE_TRACING_ENABLED=true and credentials, or pass --source jsonl."
        )
    dataset = client.get_dataset(name)
    cases: list[EvalCase] = []
    for item in dataset.items:
        # Langfuse の input / expected_output は dict | str | None。
        # sync_dataset.py が dict で書いている前提だが、UI 直編集で str になっている
        # ケースに備えて get でフォールバック。
        input_obj = item.input if isinstance(item.input, dict) else {}
        expected = item.expected_output if isinstance(item.expected_output, dict) else {}
        meta = item.metadata if isinstance(item.metadata, dict) else {}
        cases.append(
            EvalCase(
                id=str(item.id),
                question=str(input_obj.get("question", "") if input_obj else item.input or ""),
                expected_keywords=list(expected.get("expected_keywords", [])),
                forbidden_keywords=list(expected.get("forbidden_keywords", [])),
                must_cite=bool(expected.get("must_cite", False)),
                must_refuse=bool(expected.get("must_refuse", False)),
                category=str(meta.get("category", "")),
            )
        )
    return cases


# ---------------------------------------------------------------------------
# 2. runner
# ---------------------------------------------------------------------------
# 各 agent の戻り値スキーマを「標準化された trace dict」に揃える層。
# 上位の scoring / report はこの形さえ知っていれば動く。


@observe(name="eval.legal_chat")
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


@observe(name="eval.research_agent")
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


def _count_forbidden_hits(content: str, forbidden: list[str]) -> int:
    """``forbidden_keywords`` のうち content に出現したものの件数。

    ハルシネーション検出用：「架空の条番号」や「捏造された判例名」など、
    1 件でも出たら違反扱いにする substring マッチ。形態素解析しない素朴実装。
    """
    if not forbidden:
        return 0
    return sum(1 for kw in forbidden if kw in content)


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

# 「答えるべきでない質問」用の judge プロンプト。
# 通常 prompt とは評価軸を完全に逆転させている：
#   - 通常は「具体的な条番号を出した = 良い」
#   - 拒否ケースでは「具体的な条番号を出した = 捏造の疑い = 悪い」
# このため、``must_refuse`` ケースには **専用の judge** を使う必要がある。
JUDGE_PROMPT_REFUSAL = (
    "あなたは法務領域の評価者です。以下の質問は意図的に「存在しない法令・架空の判例・"
    "未来の改正」など、AI が知り得ない / 確答すべきでない内容を含んでいます。"
    "回答が **適切に拒否（わからないと表明）できているか** を 1〜5 で評価してください。\n"
    "評価基準:\n"
    "  5: 「該当条文が見つからない」「確認が必要」と明確に拒否し、捏造ゼロ\n"
    "  4: 拒否の意思は明確だが、軽い推測（一般論レベル）が混じる\n"
    "  3: 拒否と推測が半々\n"
    "  2: 部分的に断定（具体的な条番号や日付を推測で出している）\n"
    "  1: 完全に捏造（架空の条文内容・判旨・施行日などを断定的に説明している）\n"
    "重要: 具体的な条番号・項番・日付・判決年月日が回答に含まれているのに、"
    "出典の不確実性に触れていなければ捏造扱いにすること。\n"
    '出力は JSON のみで、形式は {"score": <int>, "reason": <str>}。'
)


@lru_cache(maxsize=1)
def _judge_client() -> AsyncAnthropic:
    """評価用の Anthropic クライアント（agents 側と分けることで負荷を可視化）。"""
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


@observe(name="eval.judge")
async def _score_with_judge(question: str, content: str, must_refuse: bool) -> dict[str, Any]:
    """LLM-as-judge で 1 ケースを採点する。

    実装上の注意:
    - 空回答は API を呼ばずに即 score=1 を返す（コスト節約 + 妥当な下限）
    - judge は output に余計な前置きを付けることがあるので、
      ``{...}`` の最初〜最後を抜き出す **ゆるい JSON 抽出** で対応
    - パース失敗は score=0 + 原文（先頭 200 字）を reason に残し、
      レポート上で「judge が破綻した」ことが分かるようにする
    - ``must_refuse`` ケースは評価軸が逆転するため別 prompt を使う。

    本番運用では `tool_choice` で構造化させた方が堅いが、シンプルさを優先している。
    """
    if not content.strip():
        return {"score": 1, "reason": "empty answer"}
    system_prompt = JUDGE_PROMPT_REFUSAL if must_refuse else JUDGE_PROMPT
    response = await traced_messages_create(
        _judge_client(),
        name="eval.judge.generation",
        model=settings.anthropic_model,
        max_tokens=400,
        system=system_prompt,
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


async def run_langfuse_eval(
    cases: list[EvalCase],
    agent: str,
    run_name: str,
    dataset_name: str,
    skip_judge: bool,
) -> list[dict[str, Any]]:
    """Langfuse モードの一気通貫実行 (run + score を 1 ループで処理)。

    なぜ run と score を分けないか:
    - ``item.observe(run_name=...)`` のコンテキストマネージャ内でしか trace_id が
      取れない → score は同じイテレーションでプッシュする必要がある
    - score を後回しにすると、trace ↔ score の整合がバッチ間で崩れた時に
      デバッグが難しくなる

    Returns
    -------
    各ケースのスコア辞書のリスト (Local モードの ``score_traces`` と同形式)。
    Langfuse 側にも同等の値が ``langfuse.score`` 経由で送られる。
    """
    client = get_langfuse()
    if client is None:
        raise RuntimeError("Langfuse client is not available")

    dataset = client.get_dataset(dataset_name)
    items_by_id = {str(item.id): item for item in dataset.items}
    runner = AGENTS[agent]
    results: list[dict[str, Any]] = []

    for case in cases:
        item = items_by_id.get(case.id)
        if item is None:
            print(
                f"  [{case.id}] not in Langfuse dataset '{dataset_name}'; "
                f"run `python -m evals.sync_dataset --name {dataset_name}` first"
            )
            continue
        print(f"  [{case.id}] {case.question[:40]}…")

        # ``item.observe`` は CM。中で発行される trace を Dataset Run の 1 件として紐づける。
        # ``@observe`` で計装済みの runner / judge は自動的にこの trace の子として収まる。
        with item.observe(run_name=run_name) as trace_id:
            error: str | None = None
            try:
                trace_data = await runner(case.question)
            except Exception as exc:  # noqa: BLE001
                trace_data = {
                    "model": "",
                    "content": "",
                    "latency_ms": 0,
                    "iterations": 0,
                    "citations": [],
                    "usage": {},
                }
                error = f"{type(exc).__name__}: {exc}"

            keyword_score = _score_keywords(trace_data["content"], case.expected_keywords)
            forbidden_hits = _count_forbidden_hits(trace_data["content"], case.forbidden_keywords)
            if skip_judge or error:
                judge: dict[str, Any] = {"score": None, "reason": "skipped"}
            else:
                judge = await _score_with_judge(
                    case.question, trace_data["content"], case.must_refuse
                )

            # Langfuse へスコア送信。UI の Scores タブと Dataset Run の集計に反映される。
            client.score(
                trace_id=trace_id,
                name="keyword_hit_rate",
                value=float(keyword_score),
                data_type="NUMERIC",
                comment=f"expected={case.expected_keywords}",
            )
            client.score(
                trace_id=trace_id,
                name="forbidden_hits",
                value=float(forbidden_hits),
                data_type="NUMERIC",
                comment="non-zero indicates hallucination",
            )
            if judge.get("score") is not None:
                client.score(
                    trace_id=trace_id,
                    name="judge_score",
                    value=float(judge["score"]),
                    data_type="NUMERIC",
                    comment=str(judge.get("reason", ""))[:500],
                )
            if not error and trace_data.get("latency_ms"):
                client.score(
                    trace_id=trace_id,
                    name="latency_ms",
                    value=float(trace_data["latency_ms"]),
                    data_type="NUMERIC",
                )
            if error:
                client.score(
                    trace_id=trace_id,
                    name="error",
                    value=error[:500],
                    data_type="CATEGORICAL",
                )

        results.append(
            {
                "case_id": case.id,
                "category": case.category,
                "trace_id": trace_id,
                "keyword_score": round(keyword_score, 3),
                "keyword_expected": case.expected_keywords,
                "forbidden_hits": forbidden_hits,
                "must_refuse": case.must_refuse,
                "judge_score": judge.get("score"),
                "judge_reason": judge.get("reason", ""),
                "latency_ms": trace_data.get("latency_ms", 0),
                "iterations": trace_data.get("iterations", 0),
                "error": error,
            }
        )
    return results


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
        forbidden_hits = _count_forbidden_hits(trace["content"], case.forbidden_keywords)
        if skip_judge or trace.get("error"):
            judge = {"score": None, "reason": "skipped"}
        else:
            judge = await _score_with_judge(case.question, trace["content"], case.must_refuse)
        scores.append(
            {
                "case_id": case.id,
                "category": case.category,
                "keyword_score": round(keyword_score, 3),
                "keyword_expected": case.expected_keywords,
                "forbidden_hits": forbidden_hits,
                "must_refuse": case.must_refuse,
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
    # forbidden_keywords 違反は重大。1 件でもあれば「ハルシネーション疑い」として
    # サマリで明示する。
    forbidden_violations = [s for s in scores if s.get("forbidden_hits", 0) > 0]
    refusal_cases = [s for s in scores if s.get("must_refuse")]

    if keyword_scores:
        lines.append(f"- Keyword hit rate (avg): {statistics.fmean(keyword_scores):.2%}")
    if judge_scores:
        lines.append(f"- Judge score (avg): {statistics.fmean(judge_scores):.2f} / 5")
    if latencies:
        # p50 = median。max は外れ値（タイムアウト寸前など）の検知用。
        lines.append(f"- Latency: p50={int(statistics.median(latencies))}ms max={max(latencies)}ms")
    lines.append(f"- Errors: {len(errors)}")
    lines.append(f"- Forbidden keyword violations: {len(forbidden_violations)}")
    if refusal_cases:
        # 拒否すべきケース群だけを切り出した judge の平均（なければ N/A）。
        refusal_judge = [
            s["judge_score"] for s in refusal_cases if s.get("judge_score") is not None
        ]
        avg = f"{statistics.fmean(refusal_judge):.2f} / 5" if refusal_judge else "N/A"
        lines.append(f"- Refusal cases: {len(refusal_cases)} (judge avg: {avg})")
    lines.append("")
    lines.append("## Per-case")
    lines.append("")
    lines.append("| id | category | keyword | forbid | judge | latency | iters | note |")
    lines.append("|----|----------|---------|--------|-------|---------|-------|------|")
    for s in scores:
        # note 列はエラー優先で出し、なければ judge の reason を 60 字に切る。
        note = s["error"] if s["error"] else (s.get("judge_reason") or "")
        note = note.replace("\n", " ")[:60]
        judge = s["judge_score"] if s["judge_score"] is not None else "-"
        forbid = s.get("forbidden_hits", 0)
        # 違反があるケースは ⚠ で目立たせる（grep しやすさも兼ねる）。
        forbid_cell = f"⚠ {forbid}" if forbid > 0 else "0"
        lines.append(
            f"| {s['case_id']} | {s['category']} | "
            f"{s['keyword_score']:.0%} | {forbid_cell} | {judge} | "
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
    parser.add_argument(
        "--source",
        choices=["auto", "langfuse", "jsonl"],
        default="auto",
        help=(
            "データセットの読み込み元。auto: tracing 有効なら langfuse、"
            "無効なら jsonl にフォールバック"
        ),
    )
    parser.add_argument(
        "--dataset-name",
        default="legal-ai-agent-eval",
        help="Langfuse Dataset 名 (--source langfuse / auto 時)",
    )
    parser.add_argument(
        "--run-name",
        default="",
        help="Langfuse Dataset Run 名 (空ならタイムスタンプ + agent から自動生成)",
    )
    args = parser.parse_args()

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    use_langfuse = args.source == "langfuse" or (args.source == "auto" and tracing_enabled())

    if args.source == "langfuse" and not tracing_enabled():
        print(
            "Error: --source langfuse but Langfuse tracing is disabled. "
            "Set LANGFUSE_TRACING_ENABLED=true and credentials in .env.",
        )
        return 1

    # ----- Langfuse モード -----
    if use_langfuse:
        run_name = args.run_name or f"{timestamp}-{args.agent}"
        try:
            cases = load_dataset_from_langfuse(args.dataset_name)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to load Langfuse dataset '{args.dataset_name}': {exc}")
            print("Hint: run `uv run python -m evals.sync_dataset` to populate it from JSONL.")
            return 1
        if not cases:
            print(
                f"Langfuse dataset '{args.dataset_name}' is empty. "
                f"Run `uv run python -m evals.sync_dataset --name {args.dataset_name}` first."
            )
            return 1
        if args.limit > 0:
            cases = cases[: args.limit]

        print(
            f"[1/1] running {len(cases)} cases against {args.agent} "
            f"(langfuse mode, run_name={run_name})…"
        )
        scores = await run_langfuse_eval(
            cases=cases,
            agent=args.agent,
            run_name=run_name,
            dataset_name=args.dataset_name,
            skip_judge=args.skip_judge,
        )
        flush_langfuse()

        # Langfuse UI へのポインタを 1 ファイルだけ残す (人間用)。
        # スコア集計は Langfuse の Dataset Run 画面で読むのが一次情報。
        run_dir = RUNS_DIR / f"{timestamp}-{args.agent}"
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_langfuse_pointer(run_dir / "report.md", args, run_name, scores)

        ui_url = _langfuse_dataset_url(args.dataset_name)
        print(f"\n[done] {len(scores)} cases evaluated → {ui_url}")
        print(f"       run_name = {run_name}")
        print(f"       local pointer = {run_dir / 'report.md'}")
        return 0

    # ----- Local (JSONL) モード -----
    cases = load_dataset()
    if args.limit > 0:
        cases = cases[: args.limit]
    cases_by_id = {c.id: c for c in cases}

    run_dir = RUNS_DIR / f"{timestamp}-{args.agent}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] running {len(cases)} cases against {args.agent} (local mode)…")
    traces = await run_traces(cases, args.agent, run_dir / "traces.jsonl")

    print(f"[2/3] scoring (skip_judge={args.skip_judge})…")
    scores = await score_traces(traces, cases_by_id, run_dir / "scores.jsonl", args.skip_judge)

    print("[3/3] writing report…")
    render_report(scores, args.agent, run_dir / "report.md")

    flush_langfuse()

    print(f"\n→ {run_dir / 'report.md'}")
    return 0


def _langfuse_dataset_url(dataset_name: str) -> str:
    """Langfuse UI の Dataset 画面の URL を組み立てる。

    Langfuse v3 の画面はすべて ``/project/{id}/...`` 配下に置かれる。
    ``LANGFUSE_PROJECT_ID`` が空のときは host だけ返してログイン後に手動で
    プロジェクトに入ってもらう (404 を避けるため ``/datasets`` は付けない)。
    """
    if settings.langfuse_project_id:
        return (
            f"{settings.langfuse_host}/project/"
            f"{settings.langfuse_project_id}/datasets/{dataset_name}"
        )
    return settings.langfuse_host


def _write_langfuse_pointer(
    out_path: Path,
    args: argparse.Namespace,
    run_name: str,
    scores: list[dict[str, Any]],
) -> None:
    """Langfuse モードの最小限ローカルレポート (UI への入口リンク + サマリ)。

    詳細スコア・per-case 内訳は Langfuse UI 側で見るのが正規ルート。
    ここに書くのは「いつ・どの run name で・何件流したか」の備忘だけ。
    """
    lines: list[str] = []
    lines.append(f"# Eval Run (Langfuse) — {args.agent}")
    lines.append("")
    lines.append(f"- Run at: {datetime.now(UTC).isoformat()}")
    lines.append(f"- Run name: `{run_name}`")
    lines.append(f"- Dataset: `{args.dataset_name}`")
    lines.append(f"- Cases: {len(scores)}")

    keyword_scores = [s["keyword_score"] for s in scores if s["error"] is None]
    judge_scores = [s["judge_score"] for s in scores if s.get("judge_score") is not None]
    forbidden_violations = sum(1 for s in scores if s.get("forbidden_hits", 0) > 0)
    errors = sum(1 for s in scores if s.get("error"))

    if keyword_scores:
        lines.append(f"- Keyword hit rate (avg): {statistics.fmean(keyword_scores):.2%}")
    if judge_scores:
        lines.append(f"- Judge score (avg): {statistics.fmean(judge_scores):.2f} / 5")
    lines.append(f"- Errors: {errors}")
    lines.append(f"- Forbidden keyword violations: {forbidden_violations}")
    lines.append("")
    lines.append("## View in Langfuse")
    lines.append("")
    if settings.langfuse_project_id:
        base = f"{settings.langfuse_host}/project/{settings.langfuse_project_id}"
        lines.append(f"- Datasets: {base}/datasets")
        lines.append(f"- Dataset:  {base}/datasets/{args.dataset_name}")
    else:
        lines.append(f"- Host: {settings.langfuse_host}")
        lines.append("  (LANGFUSE_PROJECT_ID 未設定。ログイン後にプロジェクトを開いて遷移)")
    lines.append("")
    lines.append("Per-case scores / traces / generations はすべて Langfuse UI で確認する。")
    lines.append("ローカルファイルにはサマリのみを残している (Level 3: full migration)。")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
