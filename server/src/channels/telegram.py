from __future__ import annotations

import time
from dataclasses import dataclass, field

from .base import ChannelAdapter


@dataclass
class TelegramChannelService:
    adapter: ChannelAdapter
    allowed_chat_ids: set[str] = field(default_factory=set)
    min_interval_sec: float = 0.5
    _last_sent_at: dict[str, float] = field(default_factory=dict)

    def can_accept(self, chat_id: str) -> tuple[bool, str]:
        if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
            return False, "인증되지 않은 채널이에요. 운영자에게 chat id 등록을 요청해 주세요."

        now = time.time()
        last = self._last_sent_at.get(chat_id, 0.0)
        if now - last < self.min_interval_sec:
            return False, "요청이 너무 빨라요. 잠시 후 다시 시도해 주세요."
        return True, ""

    def handle_message(self, chat_id: str, text: str, llm_respond) -> tuple[bool, str]:
        allowed, reason = self.can_accept(chat_id)
        if not allowed:
            return False, reason

        if not text.strip():
            return False, "비어있는 메시지는 처리할 수 없어요."

        response = llm_respond(text)
        if not self.adapter.send_text(chat_id, response):
            return False, "메시지 전송에 실패했어요."

        self._last_sent_at[chat_id] = time.time()
        return True, response
