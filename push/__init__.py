from push.base import PushChannel, get_channels

# Backward-compatible function re-exports — these delegate to the new class-based API.
from push.wecom import WeComChannel


async def send_wecom_digest(webhook_url: str, date_str: str, total_fetched: int,
                            total_selected: int, clusters: list[dict]) -> bool:
    ch = WeComChannel(webhook_url)
    return await ch.send_digest(date_str, total_fetched, total_selected, clusters)


async def send_wecom_review(webhook_url: str, week_start: str, week_end: str,
                            content: str) -> bool:
    ch = WeComChannel(webhook_url)
    return await ch.send_review(week_start, week_end, content)
