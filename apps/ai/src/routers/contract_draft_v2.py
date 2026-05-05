"""contract_draft_v2 (LangGraph 版) 用の FastAPI ルータ。

v1 (`routers/contract_draft.py`) と **同じ shape の入出力 DTO** を返すことで、
backend (Hono) からは engine の違いを意識せずに呼び分けられる。
内部実装だけが LangGraph (StateGraph) で組まれている、という構成。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..agents.contract_draft_v2 import (
    GenerateResult,
    HearingTurnInput,
    HearingTurnResult,
    generate_full_draft_v2,
    hearing_turn_v2,
)
from .contract_draft import (
    GenerateRequest,
    GenerateResponse,
    HearingRequest,
    HearingResponse,
)

router = APIRouter()


@router.post("/draft-v2/hearing", response_model=HearingResponse)
async def post_hearing_v2(req: HearingRequest) -> HearingResponse:
    """v2 ヒアリング 1 ターン。v1 と同じ DTO で返す。"""
    payload = HearingTurnInput(
        history=[h.model_dump() for h in req.history],
        user_message=req.user_message,
        current_requirements=req.current_requirements,
    )
    try:
        result: HearingTurnResult = await hearing_turn_v2(payload)
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


@router.post("/draft-v2/generate", response_model=GenerateResponse)
async def post_generate_v2(req: GenerateRequest) -> GenerateResponse:
    """v2 generate (draft → review → revise [→ revise (cond)]) を一気に実行。"""
    try:
        result: GenerateResult = await generate_full_draft_v2(req.requirements)
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
