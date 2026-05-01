"""契約書レビュー用の FastAPI ルータ。

このルータは ``agents/contract_review.py`` の ``review_contract()`` を呼ぶだけ。
強制 tool 呼び出しでスキーマ保証された出力を **HTTP レスポンス側でも再検証** する
（二重防御：``ReviewedRisk`` の Literal で severity の値域を保証）。

入力は multipart/form-data:

- ``title``: 必須テキスト
- ``body``: 任意テキスト（直貼りの場合）
- ``file``: 任意 PDF（``application/pdf`` のみ、10MB 以内）

``body`` と ``file`` は **どちらか一方必須**。両方ある場合は ``file`` を優先する。
"""

from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..agents.contract_review import review_contract
from ..utils.pdf import extract_text

router = APIRouter()

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10MB
MAX_BODY_CHARS = 200_000
ALLOWED_PDF_MIME = {"application/pdf", "application/x-pdf"}


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
async def post_review(
    title: str = Form(..., min_length=1, max_length=200),
    body: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),  # noqa: B008 — FastAPI dependency marker
) -> ReviewResponse:
    """契約書テキスト or PDF を Claude に投げ、構造化されたレビュー結果を返す。

    file が指定されていれば PDF からテキストを抽出して使う（body は無視）。
    """
    text = await _resolve_body_text(body, file)
    try:
        result = await review_contract(title, text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI call failed: {exc}") from exc
    return ReviewResponse.model_validate(result)


async def _resolve_body_text(body: str | None, file: UploadFile | None) -> str:
    """body / file から最終的な契約本文テキストを決める。

    優先順位: file > body。どちらも無ければ 400。
    """
    if file is not None and file.filename:
        if file.content_type and file.content_type not in ALLOWED_PDF_MIME:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported file type: {file.content_type} (PDF only)",
            )
        buf = await file.read()
        if len(buf) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"PDF too large: {len(buf)} bytes (max {MAX_PDF_BYTES})",
            )
        try:
            text = extract_text(buf)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif body and body.strip():
        text = body
    else:
        raise HTTPException(status_code=400, detail="either 'body' or 'file' is required")

    if len(text) > MAX_BODY_CHARS:
        # 既存の上限。長い PDF の場合は先頭から切り詰める。
        text = text[:MAX_BODY_CHARS]
    return text
