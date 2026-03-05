import pytest

from src.channels.telegram import TelegramChannelService


class _DummyAdapter:
    def __init__(self, ok=True):
        self.ok = ok
        self.sent = []

    def send_text(self, chat_id: str, text: str) -> bool:
        self.sent.append((chat_id, text))
        return self.ok


@pytest.mark.telegram
@pytest.mark.channel
def test_telegram_channel_accepts_and_sends():
    adapter = _DummyAdapter(ok=True)
    svc = TelegramChannelService(adapter=adapter, allowed_chat_ids={"42"}, min_interval_sec=0.0)

    ok, response = svc.handle_message("42", "안녕", lambda text: f"echo:{text}")

    assert ok is True
    assert response == "echo:안녕"
    assert adapter.sent == [("42", "echo:안녕")]


@pytest.mark.telegram
@pytest.mark.channel
def test_telegram_channel_rejects_unauthorized_chat():
    adapter = _DummyAdapter(ok=True)
    svc = TelegramChannelService(adapter=adapter, allowed_chat_ids={"42"})

    ok, message = svc.handle_message("99", "안녕", lambda text: text)

    assert ok is False
    assert "인증" in message
