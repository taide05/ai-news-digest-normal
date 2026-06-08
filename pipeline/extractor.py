import logging
import httpx
from readability import Document

logger = logging.getLogger(__name__)


async def extract_full_text(url: str, timeout: int = 15) -> str:
    try:
        async with httpx.AsyncClient(timeout=float(timeout), follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                }
            )
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 403, 410):
            logger.warning(f"URL returned {e.response.status_code}: {url}")
            return "[原文无法访问]"
        raise
    except httpx.TimeoutException:
        logger.warning(f"Timeout fetching: {url}")
        return "[原文加载超时]"
    except httpx.HTTPError as e:
        logger.warning(f"HTTP error fetching {url}: {e}")
        return "[原文无法访问]"

    try:
        doc = Document(html)
        text = doc.summary()
        import re
        text = re.sub(r'<[^>]+>', '', text)
        text = ' '.join(text.split())

        if len(text) < 200:
            return "[正文提取失败，请查看原网页]"
        return text
    except Exception as e:
        logger.warning(f"Readability extraction failed for {url}: {e}")
        return "[正文提取失败，请查看原网页]"
