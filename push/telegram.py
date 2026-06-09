"""Telegram push channel."""
import logging
import httpx
from .base import PushChannel

logger = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org"


def _escape_mdv2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for ch in special:
        text = text.replace(ch, '\\' + ch)
    return text


class TelegramChannel(PushChannel):
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send_digest(self, date_str: str, total_fetched: int,
                           total_selected: int, clusters: list[dict]) -> bool:
        if not self.bot_token or not self.chat_id:
            return False

        lines = []
        for c in clusters[:10]:
            label = _escape_mdv2(c.get("label", "unnamed"))
            count = len(c.get("articles", []))
            lines.append(f"\U0001f4cc *{label}* \\({count}篇\\)")
            for art in c.get("articles", [])[:3]:
                title = _escape_mdv2(art.get("title", "")[:60])
                url = art.get("url", "")
                if url:
                    lines.append(f"  \\- [{title}]({_escape_mdv2(url)})")
                else:
                    lines.append(f"  \\- {title}")

        body = "\n".join(lines) if lines else "no topics"
        text = (
            f"\U0001f916 *AI 资讯已就绪* \\| {_escape_mdv2(date_str)}\n\n"
            f"采集 {total_fetched} 篇，精选 {total_selected} 篇，{len(clusters)} 个话题：\n\n"
            f"{body}"
        )

        if len(text.encode("utf-8")) > 4000:
            text = text.encode("utf-8")[:3900].decode("utf-8", errors="ignore") + "..."

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{TELEGRAM_API}/bot{self.bot_token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": "MarkdownV2"}
                )
                resp.raise_for_status()
                result = resp.json()
                if not result.get("ok"):
                    logger.error(f"Telegram API error: {result}")
                    return False
                return True
        except httpx.HTTPError as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def send_review(self, week_start: str, week_end: str,
                           content: str) -> bool:
        if not self.bot_token or not self.chat_id:
            return False

        preview = _escape_mdv2(content[:600])
        text = (
            f"\U0001f4dd *AI 资讯周报* \\| {week_start} ~ {week_end}\n\n"
            f"{preview}\n\n"
            f"打开 Web 面板查看完整周报"
        )

        if len(text.encode("utf-8")) > 4000:
            text = text.encode("utf-8")[:3900].decode("utf-8", errors="ignore") + "..."

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{TELEGRAM_API}/bot{self.bot_token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": "MarkdownV2"}
                )
                resp.raise_for_status()
                return resp.json().get("ok", False)
        except httpx.HTTPError as e:
            logger.error(f"Telegram review send failed: {e}")
            return False
