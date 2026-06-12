from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ai.mali_agent import ask_mali, astream_mali

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mali", tags=["mali-chat"])


class ChatHistoryItem(BaseModel):
    role: str = Field(..., description="user or assistant")
    content: str


class MaliChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_id: str | None = None
    chat_history: list[ChatHistoryItem] = []


class MaliChatResponse(BaseModel):
    answer: str
    question: str
    user_id: str | None = None
    generated_at: str
    suggestions: list[str] = []


@router.post("/chat", response_model=MaliChatResponse)
def mali_chat(request: MaliChatRequest) -> MaliChatResponse:
    try:
        result = ask_mali(
            question=request.message,
            user_id=request.user_id,
            chat_history=[item.model_dump() for item in request.chat_history],
        )
        return MaliChatResponse(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Mali chat request failed")
        raise HTTPException(status_code=400, detail=f"Mali chat failed: {exc}") from exc


@router.websocket("/chat/ws")
async def mali_chat_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    while True:
        try:
            raw = await websocket.receive_text()
            try:
                payload: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid JSON payload",
                    }
                )
                continue

            message = str(payload.get("message", "")).strip()
            if not message:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Missing required field: message",
                    }
                )
                continue

            user_id = payload.get("user_id")
            chat_history = payload.get("chat_history")
            if not isinstance(chat_history, list):
                chat_history = []

            try:
                async for event in astream_mali(
                    question=message,
                    user_id=user_id,
                    chat_history=chat_history,
                ):
                    await websocket.send_json(event)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Mali chat stream failed")
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Mali stream failed: {exc}",
                    }
                )

        except WebSocketDisconnect:
            logger.info("Mali chat websocket disconnected")
            break
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected websocket error")
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"Unexpected websocket error: {exc}",
                }
            )
