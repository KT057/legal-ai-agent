"""ReAct リサーチエージェント用の FastAPI ルータ。

このルータは ``agents/research_agent.py`` の ``research()`` を呼ぶだけの薄い層。
``max_iterations`` を **API レイヤーで上限を切る** ことで、悪意/バグで巨大な値を
渡されてもサーバが暴走しない設計になっている。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..agents.research_agent import research

router = APIRouter()


class ResearchRequest(BaseModel):
    """``POST /research`` の入力スキーマ。

    Field の制約はリクエスト境界での DoS 対策も兼ねる：
    - question 4000 字: 法令検索の質問としては十分、ペイロード爆撃を防ぐ
    - max_iterations 10: ReAct 暴走を ``research()`` 内のガード（5）の倍までに抑える
    """

    question: str = Field(min_length=1, max_length=4000)
    max_iterations: int = Field(default=5, ge=1, le=10)


class ResearchResponse(BaseModel):
    """``POST /research`` の出力スキーマ。``iterations`` で何往復したか分かる。"""

    model: str
    content: str
    iterations: int


@router.post("/research", response_model=ResearchResponse)
async def post_research(req: ResearchRequest) -> ResearchResponse:
    """ReAct ループを起動して最終回答を返す。"""
    try:
        result = await research(req.question, max_iterations=req.max_iterations)
    except ValueError as exc:
        # question が空など、クライアントの入力エラー。
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Anthropic / Voyage / DB の障害。
        raise HTTPException(status_code=502, detail=f"AI call failed: {exc}") from exc
    return ResearchResponse.model_validate(result)
