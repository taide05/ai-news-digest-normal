import pytest
from unittest.mock import patch, AsyncMock


def test_push_channel_abc_cannot_instantiate():
    from push.base import PushChannel
    with pytest.raises(TypeError):
        PushChannel()


def test_wecom_channel_has_name():
    from push.wecom import WeComChannel
    ch = WeComChannel("http://example.com/webhook")
    assert ch.name == "wecom"
    assert ch.webhook_url == "http://example.com/webhook"


def test_telegram_channel_has_name():
    from push.telegram import TelegramChannel
    ch = TelegramChannel("token123", "chat456")
    assert ch.name == "telegram"
    assert ch.bot_token == "token123"
    assert ch.chat_id == "chat456"


def test_get_channels_no_config():
    from push.base import get_channels
    from config import Config
    cfg = Config()
    channels = get_channels(cfg)
    assert channels == []


def test_get_channels_with_wecom():
    from push.base import get_channels
    from config import Config
    cfg = Config(wecom_webhook_url="http://example.com/webhook")
    channels = get_channels(cfg)
    assert len(channels) == 1
    assert channels[0].name == "wecom"


def test_get_channels_with_both():
    from push.base import get_channels
    from config import Config
    cfg = Config(
        wecom_webhook_url="http://example.com/webhook",
        telegram_bot_token="tok", telegram_chat_id="chat"
    )
    channels = get_channels(cfg)
    assert len(channels) == 2


def test_backward_compat_send_wecom_digest():
    """Verify push.py still exports send_wecom_digest."""
    from push import send_wecom_digest
    assert callable(send_wecom_digest)


def test_backward_compat_send_telegram_digest():
    """Verify push_telegram.py still exports send_telegram_digest."""
    from push_telegram import send_telegram_digest
    assert callable(send_telegram_digest)


def test_telegram_escape_mdv2():
    from push.telegram import _escape_mdv2
    result = _escape_mdv2("Hello_World*Test")
    assert "\\_" in result
    assert "\\*" in result
