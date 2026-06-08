import logging
import httpx

logger = logging.getLogger(__name__)


async def send_wecom_digest(webhook_url: str, date_str: str, total_fetched: int,
                            total_selected: int, clusters: list[dict]) -> bool:
    if not webhook_url:
        logger.warning("Webhook URL not configured, skipping push")
        return False

    cluster_lines = []
    for c in clusters[:10]:
        label = c.get("label", "未命名")
        count = len(c.get("articles", []))
        cluster_lines.append(f"\U0001f4cc {label} ({count}篇)")

    topics_text = "\n".join(cluster_lines) if cluster_lines else "暂无话题聚类"
    content = f"""\U0001f916 AI 资讯已就绪 | {date_str}

今日采集 {total_fetched} 篇，精选 {total_selected} 篇，{len(clusters)} 个话题：

{topics_text}

\U0001f4bb 打开电脑上的 Web 面板查看详情"""

    content_bytes = content.encode("utf-8")
    if len(content_bytes) > 3000:
        content = content_bytes[:2900].decode("utf-8", errors="ignore") + "..."

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                webhook_url,
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
