"""契約書レビュー用の FastAPI ルータ。

このルータも ``agents/contract_review.py`` の ``review_contract()`` を呼ぶだけ。
強制 tool 呼び出しでスキーマ保証された出力を **HTTP レスポンス側でも再検証** する
（二重防御：``ReviewedRisk`` の Literal で severity の値域を保証）。
"""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..agents.contract_review import review_contract

router = APIRouter()


class ReviewRequest(BaseModel):
    """``POST /review`` の入力スキーマ。

    body の上限 200,000 字は概ね 60〜80 ページ相当の契約まで対応できる想定。
    Anthropic のコンテキスト窓・コストを考えるとこれ以上は分割が望ましい。
    """

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=200_000)


class ReviewedRisk(BaseModel):
    """1 件のリスク指摘。``severity`` の値域は Literal で保証。

    エージェント側の REPORT_TOOL の input_schema enum と一致させること。
    片方だけ更新すると不整合で 502 が出る。
    """

    clause: str
    severity: Literal["low", "medium", "high"]
    reason: str
    suggestion: str


class ReviewResponse(BaseModel):
    """``POST /review`` の出力スキーマ。総評と複数のリスク。"""

    model: str
    summary: str
    risks: list[ReviewedRisk]


@router.post("/review", response_model=ReviewResponse)
async def post_review(req: ReviewRequest) -> ReviewResponse:
    """契約書テキストを Claude に投げ、構造化されたレビュー結果を返す。"""
    try:
        result = await review_contract(req.title, req.body)
    except Exception as exc:
        # ``review_contract`` は ValueError を投げない設計なので 502 のみ。
        # tool_use ブロックが返らなかった RuntimeError もここで 502 になる。
        raise HTTPException(status_code=502, detail=f"AI call failed: {exc}") from exc
    return ReviewResponse.model_validate(result)
