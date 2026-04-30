from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..agents.research_agent import research

router = APIRouter()


class ResearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    max_iterations: int = Field(default=5, ge=1, le=10)


class ResearchResponse(BaseModel):
    model: str
    content: str
    iterations: int


@router.post("/research", response_model=ResearchResponse)
async def post_research(req: ResearchRequest) -> ResearchResponse:
    try:
        result = await research(req.question, max_iterations=req.max_iterations)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI call failed: {exc}") from exc
    return ResearchResponse.model_validate(result)
