import asyncio
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..app import get_agent, broadcast, _loop
from src.turn_dispatch import generate_turn_response
from ..auth import require_auth

router = APIRouter(prefix="/api/chat", dependencies=[Depends(require_auth)])


class ChatMessage(BaseModel):
    text: str
    speaker_id: str = "web_user"
    language: Literal["auto", "ko", "en", "zh", "ja", "es"] | None = None


@router.post("/")
def chat(body: ChatMessage):
    agent = get_agent()
    runtime_controller = getattr(agent, "runtime_controller", None)
    runtime_response = runtime_controller.handle_text_command(body.text) if runtime_controller is not None else None
    if runtime_response:
        response, intent = runtime_response, "runtime_config"
    else:
        response, intent = generate_turn_response(agent, getattr(agent, 'robotics_runtime', None),
                                                  body.text, body.language, body.speaker_id)
    emotion = agent.emotion_system.current_emotion

    # Broadcast chat event to WebSocket clients
    from ..app import _loop as loop
    if loop is not None and loop.is_running():
        asyncio.run_coroutine_threadsafe(
            broadcast({
                "event": "chat_response",
                "text": body.text,
                "response": response,
                "intent": intent,
                "emotion": emotion,
                "speaker_id": body.speaker_id,
            }),
            loop,
        )

    return {
        "response": response,
        "intent": intent,
        "emotion": emotion,
    }
