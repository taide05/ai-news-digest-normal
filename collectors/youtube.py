import asyncio
import base64
import logging
import os
import re
import shutil
import subprocess
import tempfile
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
        self._db_conn = None
        self._budget = None
        self._whisper_enabled = False
        self._whisper_model = "openai/whisper-large-v3"
        self._max_duration_s = 1200
        self._openrouter_key = ""

    def configure(self, db_conn=None, budget=None):
        """Set runtime context — called by orchestrator before fetch()."""
        self._db_conn = db_conn
        self._budget = budget
        if db_conn:
            from db.models import get_setting
            self._openrouter_key = get_setting(db_conn, "llm.api_key", "")
            self._whisper_enabled = (
                get_setting(db_conn, "youtube.whisper_enabled", "false").lower() == "true"
            )
            self._whisper_model = get_setting(db_conn, "youtube.whisper_model", "openai/whisper-large-v3")
            try:
                self._max_duration_s = int(get_setting(db_conn, "youtube.whisper_max_duration", "1200"))
            except (ValueError, TypeError):
                self._max_duration_s = 1200

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
            if self._whisper_enabled and self._openrouter_key:
                return await self._transcribe_via_whisper(video_id)
            return ""

    async def _transcribe_via_whisper(self, video_id: str) -> str:
        """Fallback: download audio via yt-dlp, transcribe via OpenRouter Whisper."""
        if not shutil.which("yt-dlp"):
            logger.warning("Whisper fallback: yt-dlp not found on PATH, skipping")
            return ""

        if self._budget:
            estimated_cost = 0.01  # ~$0.01 per minute of audio
            if not self._budget.can_spend(estimated_cost):
                logger.warning("Whisper fallback: budget exhausted, skipping")
                return ""

        url = f"https://www.youtube.com/watch?v={video_id}"
        tmpdir = tempfile.mkdtemp(prefix="yt-whisper-")
        audio_path = os.path.join(tmpdir, "audio.m4a")

        try:
            # Download audio
            cmd = [
                "yt-dlp", "--extract-audio", "--audio-format", "m4a",
                "--quiet", "--no-warnings",
                "--match-filter", f"duration<={self._max_duration_s}",
                "-o", audio_path, url,
            ]
            loop = asyncio.get_running_loop()
            proc = await loop.run_in_executor(None, lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=120))
            if proc.returncode != 0 or not os.path.isfile(audio_path):
                logger.debug(f"yt-dlp failed for {video_id}: {proc.stderr[:200] if proc.stderr else 'no audio file'}")
                return ""

            # Read and encode audio
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("ascii")

            # Call OpenRouter Whisper
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/transcriptions",
                    headers={
                        "Authorization": f"Bearer {self._openrouter_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._whisper_model,
                        "input_audio": {"data": audio_b64, "format": "m4a"},
                        "language": self.language or "en",
                    },
                )
                if resp.status_code != 200:
                    logger.warning(f"Whisper API returned {resp.status_code}: {resp.text[:200]}")
                    return ""

                data = resp.json()
                text = data.get("text", "")

            # Record cost
            tokens = len(text.split()) if text else 0
            if self._budget and tokens > 0:
                cost = max(0.001, tokens / 1000 * 0.001)  # ~$0.001/1K tokens for Whisper
                self._budget.record_spend(self._whisper_model, tokens, cost, "whisper")

            return text

        except Exception as e:
            logger.warning(f"Whisper fallback failed for {video_id}: {e}")
            return ""
        finally:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass


register(YouTubeCollector("youtube-two-minute-papers", "UCbfYPyITQ-7l4upoX8nvctg", language="en"))
