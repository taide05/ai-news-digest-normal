from datetime import datetime
import logging
import httpx
from bs4 import BeautifulSoup
from .base import BaseCollector, Article
from .registry import register

logger = logging.getLogger(__name__)


class GitHubTrendingCollector(BaseCollector):
    name = "github-trending"
    type = "web"
    rate_limit = 2.0

    def __init__(self):
        self.url = "https://github.com/trending/python?since=daily"

    async def fetch(self, since: datetime) -> list[Article]:
        articles = []
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    self.url,
                    headers={"User-Agent": "ai-news-digest/0.3"}
                )
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f"GitHub Trending fetch failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        seen = set()
        for article_elem in soup.select("article.Box-row"):
            h2 = article_elem.select_one("h2 a")
            if not h2:
                continue

            href = h2.get("href", "").strip()
            # href is like "/owner/repo"
            full_name = href.strip("/")
            parts = full_name.split("/")
            if len(parts) != 2:
                continue

            owner, repo = parts
            full_name_lower = full_name.lower()
            if full_name_lower in seen:
                continue
            seen.add(full_name_lower)

            title = f"{owner}/{repo}"
            url = f"https://github.com{href}"

            desc_elem = article_elem.select_one("p")
            summary = desc_elem.text.strip() if desc_elem else ""

            lang_elem = article_elem.select_one('[itemprop="programmingLanguage"]')
            lang = lang_elem.text.strip() if lang_elem else ""

            stars_elem = article_elem.select_one(".octicon-star")
            stars = ""
            if stars_elem and stars_elem.parent:
                stars = stars_elem.parent.get_text(strip=True)

            content = f"Language: {lang}\nStars: {stars}\n\n{summary}" if lang or stars or summary else None

            articles.append(Article(
                source_id=self.name,
                url=url,
                title=title,
                summary=summary,
                author=owner,
                published_at=datetime.now().isoformat(),
                language="en",
                content=content,
            ))

        return articles


register(GitHubTrendingCollector())
