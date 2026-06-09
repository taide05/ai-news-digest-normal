import pytest
from push_telegram import _escape_mdv2, send_telegram_digest, send_telegram_review


class TestEscapeMDV2:
    def test_escapes_special_chars(self):
        result = _escape_mdv2("hello_world*test")
        assert result == "hello\\_world\\*test"

    def test_preserves_normal_text(self):
        result = _escape_mdv2("Hello World 123")
        assert result == "Hello World 123"


class TestSendTelegramDigest:
    @pytest.mark.asyncio
    async def test_empty_token_returns_false(self):
        result = await send_telegram_digest("", "", "2026-06-09", 10, 5, [])
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_chat_id_returns_false(self):
        result = await send_telegram_digest("token123", "", "2026-06-09", 10, 5, [])
        assert result is False
