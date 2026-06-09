from datetime import datetime
import asyncio
import logging
import httpx
from .base import BaseCollector, Article
from .registry import register

logger = logging.getLogger(__name__)

AI_KEYWORDS = ["ai", "llm", "gpt", "ml", "machine learning", "openai", "deep learning",
               "transformer", "neural", "claude", "gemini", "llama", "mistral", "diffusion",
               "rlhf", "fine-tuning", "rag", "agent", "embeddings", "vector", "anthropic",
               "deepseek", "qwen", "stable diffusion", "langchain"]


class HackerNewsCollector(BaseCollector):
    name = "hackernews"
    type = "api"
    rate_limit = 0.1

    def __init__(self):
        self.base_url = "https://hacker-news.firebaseio.com/v0"

    def _is_ai_related(self, title: str) -> bool:
        tl = title.lower()
        return any(kw in tl for kw in AI_KEYWORDS)

    async def _fetch_item(self, client: httpx.AsyncClient, item_id: int,
                          since: datetime) -> Article | None:
        try:
            resp = await client.get(f"{self.base_url}/item/{item_id}.json")
            resp.raise_for_status()
            item = resp.json()
        except httpx.HTTPError:
            return None

        if item is None or item.get("type") != "story":
            return None

        title = item.get("title", "")
        if not self._is_ai_related(title):
            return None

        pub_ts = item.get("time", 0)
        pub_dt = datetime.fromtimestamp(pub_ts) if pub_ts else None
        if pub_dt and pub_dt < since:
            return None

        return Article(
            source_id=self.name,
            url=item.get("url", f"https://news.ycombinator.com/item?id={item_id}"),
            title=title,
            summary="",
            author=item.get("by"),
            published_at=pub_dt.isoformat() if pub_dt else None,
            language="en",
        )

    async def fetch(self, since: datetime) -> list[Article]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.base_url}/newstories.json")
                resp.raise_for_status()
                ids = resp.json()[:100]
        except httpx.HTTPError as e:
            logger.warning(f"HN fetch failed: {e}")
            return []

        async with httpx.AsyncClient(timeout=10.0, limits=httpx.Limits(max_connections=20)) as client:
            tasks = [self._fetch_item(client, iid, since) for iid in ids]
            results = await asyncio.gather(*tasks)

        return [r for r in results if r is not None]


register(HackerNewsCollector())
