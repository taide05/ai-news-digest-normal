import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from push import send_wecom_digest


class TestSendWecomDigest:
    @pytest.mark.asyncio
    async def test_empty_webhook_url_returns_false(self):
        result = await send_wecom_digest("", "2026-06-09", 10, 5, [])
        assert result is False

    @pytest.mark.asyncio
    async def test_successful_push_returns_true(self):
        clusters = [
            {"label": "AI Open Source", "articles": [
                {"title": "OpenAI releases model", "url": "https://example.com/1"}
            ]}
        ]
        with patch("push.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock()
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = {"errcode": 0}
            result = await send_wecom_digest(
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                "2026-06-09", 10, 5, clusters
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_wecom_error_response_returns_false(self):
        with patch("push.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock()
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = {"errcode": 40001}
            result = await send_wecom_digest(
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                "2026-06-09", 10, 5, []
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")

        with patch("push.httpx.AsyncClient", return_value=mock_client):
            result = await send_wecom_digest(
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                "2026-06-09", 10, 5, []
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_markdown_links_included(self):
        clusters = [
            {"label": "AI", "articles": [
                {"title": "Test Article", "url": "https://example.com/1"}
            ]}
        ]
        with patch("push.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock()
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = {"errcode": 0}
            await send_wecom_digest(
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                "2026-06-09", 10, 5, clusters
            )
            call_args = mock_post.call_args[1]["json"]["markdown"]["content"]
            assert "[Test Article](https://example.com/1)" in call_args
