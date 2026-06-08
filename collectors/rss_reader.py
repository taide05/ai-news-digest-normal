from datetime import datetime
import logging
import feedparser
import httpx
from .base import BaseCollector, Article
from .registry import register

logger = logging.getLogger(__name__)


class RSSCollector(BaseCollector):
    type = "rss"
    rate_limit = 1.0

    def __init__(self, name: str, feed_url: str, language: str = "en"):
        self.name = name
        self.feed_url = feed_url
        self.language = language

    async def fetch(self, since: datetime) -> list[Article]:
        articles = []
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(self.feed_url, headers={"User-Agent": "ai-news-digest/0.1"})
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f"RSS fetch failed for {self.name}: {e}")
            return []

        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            pub = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub = datetime(*entry.published_parsed[:6]).isoformat()
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                pub = datetime(*entry.updated_parsed[:6]).isoformat()

            if pub:
                try:
                    pub_dt = datetime.fromisoformat(pub)
                    if pub_dt < since:
                        continue
                except ValueError:
                    pass

            content = None
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")

            articles.append(Article(
                source_id=self.name,
                url=getattr(entry, "link", ""),
                title=getattr(entry, "title", "").strip(),
                summary=getattr(entry, "summary", "") or getattr(entry, "description", ""),
                author=getattr(entry, "author", None),
                published_at=pub,
                language=self.language,
                content=content,
            ))

        return articles


register(RSSCollector("jiqizhixin", "https://www.jiqizhixin.com/rss", language="zh"))
register(RSSCollector("reddit-ml", "https://www.reddit.com/r/MachineLearning/.rss", language="en"))
