import pytest
from push_telegram import _escape_mdv2, send_telegram_digest, send_telegram_review


class TestEscapeMDV2:
    def test_escapes_special_chars(self):
        result = _escape_mdv2("hello_world*test")
        assert result == "hello\\_world\\*test"

    def test_preserves_normal_text(self):
        result = _escape_mdv2("Hello World 123")
        assert result == "Hello World 123"


class TestEscapeMDV2Full:
    def test_all_18_special_chars_escaped(self):
        special_chars = '_*[]()~`>#+-=|{}.!'
        result = _escape_mdv2(special_chars)
        for ch in special_chars:
            assert '\\' + ch in result, f"Character '{ch}' not escaped in: {result}"

    def test_url_with_special_chars(self):
        result = _escape_mdv2("https://example.com/path?q=1&b=2")
        assert result == "https://example\\.com/path?q\\=1&b\\=2"

    def test_markdown_link_syntax_escaped(self):
        result = _escape_mdv2("[click](url)")
        assert result == "\\[click\\]\\(url\\)"

    def test_backtick_escaped(self):
        result = _escape_mdv2("`code`")
        assert result == "\\`code\\`"

    def test_pipe_escaped(self):
        result = _escape_mdv2("a|b")
        assert result == "a\\|b"

    def test_exclamation_escaped(self):
        result = _escape_mdv2("Hello!")
        assert result == "Hello\\!"


class TestSendTelegramDigest:
    @pytest.mark.asyncio
    async def test_empty_token_returns_false(self):
        result = await send_telegram_digest("", "", "2026-06-09", 10, 5, [])
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_chat_id_returns_false(self):
        result = await send_telegram_digest("token123", "", "2026-06-09", 10, 5, [])
        assert result is False


class TestSendTelegramReview:
    @pytest.mark.asyncio
    async def test_empty_token_returns_false(self):
        result = await send_telegram_review("", "", "2026-06-01", "2026-06-07", "content")
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_chat_id_returns_false(self):
        result = await send_telegram_review("token123", "", "2026-06-01", "2026-06-07", "content")
        assert result is False
