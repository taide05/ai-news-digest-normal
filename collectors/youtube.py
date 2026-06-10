import asyncio
import logging
import re
import httpx
import feedparser
from datetime import datetime
from .base import BaseCollector, Article
from .registry import register

logger = logging.getLogger(__name__)


class YouTubeCollector(BaseCollector):
    type = "rss"
    rate_limit = 1.0

    def __init__(self, name: str, channel_id: str, language: str = "en"):
        self.name = name
        self.channel_id = channel_id
        self.language = language
        self.feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    async def fetch(self, since: datetime) -> list[Article]:
        articles = []
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(self.feed_url, headers={"User-Agent": "ai-news-digest/0.1"})
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f"YouTube RSS fetch failed for {self.name}: {e}")
            return []

        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            pub = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub = datetime(*entry.published_parsed[:6]).isoformat()
            if pub:
                try:
                    if datetime.fromisoformat(pub) < since:
                        continue
                except ValueError:
                    pass
            video_id = self._extract_video_id(getattr(entry, "link", ""))
            transcript = ""
            if video_id:
                transcript = await self._fetch_transcript(video_id)
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            articles.append(Article(
                source_id=self.name,
                url=getattr(entry, "link", ""),
                title=getattr(entry, "title", "").strip(),
                summary=summary[:200] if summary else "",
                author=getattr(entry, "author", None),
                published_at=pub,
                language=self.language,
                content=transcript if transcript else summary,
            ))
        return articles

    @staticmethod
    def _extract_video_id(url: str) -> str | None:
        patterns = [r'v=([a-zA-Z0-9_-]{11})', r'youtu\.be/([a-zA-Z0-9_-]{11})', r'/shorts/([a-zA-Z0-9_-]{11})']
        for p in patterns:
            m = re.search(p, url)
            if m:
                return m.group(1)
        return None

    async def _fetch_transcript(self, video_id: str) -> str:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            loop = asyncio.get_running_loop()
            transcript = await loop.run_in_executor(
                None, lambda: YouTubeTranscriptApi.get_transcript(video_id, languages=[self.language, 'en'])
            )
            return " ".join(entry["text"] for entry in transcript)
        except Exception as e:
            logger.debug(f"Transcript fetch failed for {video_id}: {e}")
            return ""


register(YouTubeCollector("youtube-two-minute-papers", "UCbfYPyITQ-7l4upoX8nvctg", language="en"))
