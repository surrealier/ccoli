from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class BaseChannelMessage:
    channel: str
    user_id: str
    text: str


class ChannelAdapter(Protocol):
    def send_text(self, chat_id: str, text: str) -> bool:
        ...
