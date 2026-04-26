from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..agents.legal_chat import ChatTurn, reply

router = APIRouter()


class ChatRequest(BaseModel):
    messages: list[ChatTurn]


class ChatResponse(BaseModel):
    model: str
    content: str


@router.post("/chat", response_model=ChatResponse)
async def post_chat(req: ChatRequest) -> ChatResponse:
    try:
        result = await reply(req.messages)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI call failed: {exc}") from exc
    return ChatResponse.model_validate(result)
