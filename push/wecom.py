"""WeCom (企业微信) push channel."""
import logging
import httpx
from .base import PushChannel

logger = logging.getLogger(__name__)
MAX_LEN = 3900  # wecom markdown limit is 4096, leave margin


class WeComChannel(PushChannel):
    name = "wecom"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_digest(self, date_str: str, total_fetched: int,
                           total_selected: int, clusters: list[dict]) -> bool:
        if not self.webhook_url:
            logger.warning("Webhook URL not configured, skipping push")
            return False

        cluster_lines = []
        for c in clusters[:10]:
            label = c.get("label", "未命名")
            articles = c.get("articles", [])
            count = len(articles)
            cluster_lines.append(f"\U0001f4cc {label} ({count}篇)")
            for art in articles[:3]:
                title = art.get("title", "")[:50]
                url = art.get("url", "")
                if url:
                    cluster_lines.append(f"  > [{title}]({url})")
                else:
                    cluster_lines.append(f"  > {title}")

        topics_text = "\n".join(cluster_lines) if cluster_lines else "暂无话题聚类"
        header = f"""\U0001f916 AI 资讯已就绪 | {date_str}

今日采集 {total_fetched} 篇，精选 {total_selected} 篇，{len(clusters)} 个话题：

{topics_text}
"""

        footer = "\n\n\U0001f4bb 打开电脑 Web 面板查看详情"

        # trim to fit wecom limit, keeping footer intact
        content = header + footer
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > MAX_LEN:
            header_bytes = header.encode("utf-8")
            available = MAX_LEN - len(footer.encode("utf-8"))
            while len(header_bytes) > available:
                cluster_lines.pop()
                header = "\n".join([
                    f"\U0001f916 AI 资讯已就绪 | {date_str}",
                    "",
                    f"今日采集 {total_fetched} 篇，精选 {total_selected} 篇，{len(clusters)} 个话题：",
                    "",
                    "\n".join(cluster_lines),
                    "",
                ])
                header_bytes = header.encode("utf-8")
            content = header + footer

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self.webhook_url,
                    json={"msgtype": "markdown", "markdown": {"content": content}}
                )
                resp.raise_for_status()
                result = resp.json()
                if result.get("errcode") != 0:
                    logger.error(f"WeCom webhook error: {result}")
                    return False
                return True
        except httpx.HTTPError as e:
            logger.error(f"WeCom webhook send failed: {e}")
            return False

    async def send_review(self, week_start: str, week_end: str,
                           content: str) -> bool:
        if not self.webhook_url:
            return False

        preview = content[:800] + ("..." if len(content) > 800 else "")
        msg = (
            f"## AI 资讯周报 | {week_start} ~ {week_end}\n\n"
            f"{preview}\n\n"
            f"[打开 Web 面板查看完整周报](http://127.0.0.1:8765/review)"
        )

        msg_bytes = msg.encode("utf-8")
        if len(msg_bytes) > 3900:
            msg = msg_bytes[:3800].decode("utf-8", errors="ignore") + "..."

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self.webhook_url,
                    json={"msgtype": "markdown", "markdown": {"content": msg}}
                )
                resp.raise_for_status()
                result = resp.json()
                return result.get("errcode") == 0
        except httpx.HTTPError as e:
            logger.error(f"WeCom review push failed: {e}")
            return False
