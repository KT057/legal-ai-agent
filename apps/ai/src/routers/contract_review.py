from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..agents.contract_review import review_contract

router = APIRouter()


class ReviewRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=200_000)


class ReviewedRisk(BaseModel):
    clause: str
    severity: Literal["low", "medium", "high"]
    reason: str
    suggestion: str


class ReviewResponse(BaseModel):
    model: str
    summary: str
    risks: list[ReviewedRisk]


@router.post("/review", response_model=ReviewResponse)
async def post_review(req: ReviewRequest) -> ReviewResponse:
    try:
        result = await review_contract(req.title, req.body)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI call failed: {exc}") from exc
    return ReviewResponse.model_validate(result)
