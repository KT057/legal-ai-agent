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


class ResearchCitation(BaseModel):
    """ReAct ループ中に ``search_laws`` で引いた条文 1 件分。

    フィールドは ``rag/retriever.py`` の ``Citation`` dataclass と 1:1 対応する。
    ``research_agent.research()`` が ``[asdict(c) for c in citations_seen]`` で
    dict 化したものを Pydantic でそのまま受け直す形。
    """

    law_id: str
    law_title: str
    law_num: str
    article_no: str | None
    article_title: str | None
    body: str
    source_url: str
    score: float


class ResearchResponse(BaseModel):
    """``POST /research`` の出力スキーマ。``iterations`` で何往復したか分かる。

    ``citations`` は ReAct ループ中に集めた全引用条文（ラウンドをまたいで連番）。
    モデルが本文中で ``[citation_id=N]`` 形式で参照する N と、この配列の
    1-origin index が対応する。
    """

    model: str
    content: str
    iterations: int
    citations: list[ResearchCitation]


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
