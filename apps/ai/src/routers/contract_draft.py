"""NDA ドラフト生成エージェント用の FastAPI ルータ。

設計方針：このルータも他と同様に **薄く** 保ち、本体は ``agents/contract_draft.py``
に集約する。eval ハーネスから直接 ``generate_from_requirements()`` を呼べる
ようにするため、HTTP 境界には業務ロジックを書かない。

エンドポイント：

* ``POST /draft/hearing`` — 1 ターン分のヒアリング会話を進める
* ``POST /draft/generate`` — 確定要件を受け取り、draft → review → revise を一気に実行
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from ..agents.contract_draft import (
    GenerateResult,
    HearingTurnInput,
    HearingTurnResult,
    RequirementsDraft,
    generate_full_draft,
    hearing_turn,
)

router = APIRouter()


def _camel_config() -> ConfigDict:
    """API 境界の DTO は camelCase で受け渡す共通設定。"""
    return ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class HearingHistoryItem(BaseModel):
    model_config = _camel_config()

    role: str
    content: str


class HearingRequest(BaseModel):
    """``POST /draft/hearing`` の入力。

    * ``history`` はこれまでの会話 (フロントが保持しているもの) を丸ごと渡す
    * ``currentRequirements`` は現時点で確定済みの要件 (なければ空)
    * ``userMessage`` は今ターンのユーザー発話
    """

    model_config = _camel_config()

    history: list[HearingHistoryItem] = []
    user_message: str
    current_requirements: RequirementsDraft = RequirementsDraft()


class HearingResponse(BaseModel):
    """``POST /draft/hearing`` の出力。"""

    model_config = _camel_config()

    model: str
    assistant_message: str
    requirements: RequirementsDraft
    is_complete: bool
    pending_question: str | None = None
    missing_field: str | None = None


class GenerateRequest(BaseModel):
    """``POST /draft/generate`` の入力。確定済み要件を渡す。"""

    model_config = _camel_config()

    requirements: RequirementsDraft


class GenerateResponse(BaseModel):
    """``POST /draft/generate`` の出力。3 phase 分の成果物。"""

    model_config = _camel_config()

    model: str
    draft_v1: str
    risks: list[dict]
    review_summary: str
    final_draft: str
    latency_ms: int


@router.post("/draft/hearing", response_model=HearingResponse)
async def post_hearing(req: HearingRequest) -> HearingResponse:
    """ヒアリングを 1 ターン進める。"""
    payload = HearingTurnInput(
        history=[h.model_dump() for h in req.history],
        user_message=req.user_message,
        current_requirements=req.current_requirements,
    )
    try:
        result: HearingTurnResult = await hearing_turn(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI call failed: {exc}") from exc

    return HearingResponse(
        model=result.model,
        assistant_message=result.assistant_message,
        requirements=result.requirements,
        is_complete=result.is_complete,
        pending_question=result.pending_question,
        missing_field=result.missing_field,
    )


@router.post("/draft/generate", response_model=GenerateResponse)
async def post_generate(req: GenerateRequest) -> GenerateResponse:
    """確定済み要件から draft → review → revise を実行。"""
    try:
        result: GenerateResult = await generate_full_draft(req.requirements)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI call failed: {exc}") from exc

    return GenerateResponse(
        model=result.model,
        draft_v1=result.draft_v1,
        risks=result.risks,
        review_summary=result.review_summary,
        final_draft=result.final_draft,
        latency_ms=result.latency_ms,
    )
