"""法務相談チャット用の FastAPI ルータ（HTTP 境界）。

設計方針：このルータは **薄く** 保ち、本体ロジックは ``agents/legal_chat.py``
に集約する。理由は eval や CLI から同じ ``reply()`` を直接呼べるようにするため
（HTTP ハンドラに業務ロジックを書くと再利用が効かない）。

エラー分類のルール:
* ``ValueError`` → 400（クライアントのリクエストが不正、再送しても直らない）
* それ以外 → 502（依存サービス起因の失敗、リトライで復旧する可能性あり）
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..agents.legal_chat import ChatTurn, reply

router = APIRouter()


class ChatRequest(BaseModel):
    """``POST /chat`` の入力スキーマ。会話履歴を丸ごと受け取る。"""

    messages: list[ChatTurn]


class ChatResponse(BaseModel):
    """``POST /chat`` の出力スキーマ。使用モデル名と回答テキスト。"""

    model: str
    content: str


@router.post("/chat", response_model=ChatResponse)
async def post_chat(req: ChatRequest) -> ChatResponse:
    """会話履歴を渡して Claude の応答を返すエンドポイント。"""
    try:
        result = await reply(req.messages)
    except ValueError as exc:
        # 「messages が空」「最後が user じゃない」等のクライアント側の不正。
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Anthropic API ダウン / Voyage 401 / DB 接続失敗など、依存サービスの障害。
        # 502 にしてクライアントにリトライ可能性を伝える。
        raise HTTPException(status_code=502, detail=f"AI call failed: {exc}") from exc
    return ChatResponse.model_validate(result)
