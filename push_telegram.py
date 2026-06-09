"""Backward-compatible re-exports. New code should use push.telegram.TelegramChannel."""
from push.telegram import TelegramChannel, _escape_mdv2


async def send_telegram_digest(bot_token: str, chat_id: str, date_str: str,
                                total_fetched: int, total_selected: int,
                                clusters: list[dict]) -> bool:
    ch = TelegramChannel(bot_token, chat_id)
    return await ch.send_digest(date_str, total_fetched, total_selected, clusters)


async def send_telegram_review(bot_token: str, chat_id: str,
                                week_start: str, week_end: str,
                                content: str) -> bool:
    ch = TelegramChannel(bot_token, chat_id)
    return await ch.send_review(week_start, week_end, content)
