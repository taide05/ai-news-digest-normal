"""Push channel abstraction."""
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("push")


class PushChannel(ABC):
    """Abstract push channel for digests and reviews."""

    name: str = "base"

    @abstractmethod
    async def send_digest(self, date_str: str, total_fetched: int,
                           total_selected: int, clusters: list[dict]) -> bool:
        """Send daily digest. Return True on success."""
        ...

    async def send_review(self, week_start: str, week_end: str,
                           content: str) -> bool:
        """Send weekly review. Optional — default no-op."""
        return False


def get_channels(cfg) -> list[PushChannel]:
    """Return active push channels based on config."""
    channels = []

    if cfg.wecom_webhook_url:
        from push.wecom import WeComChannel
        channels.append(WeComChannel(cfg.wecom_webhook_url))

    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        from push.telegram import TelegramChannel
        channels.append(TelegramChannel(cfg.telegram_bot_token, cfg.telegram_chat_id))

    return channels
