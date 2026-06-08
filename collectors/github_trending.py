from datetime import datetime
import logging
import httpx
import re
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
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "text/html",
                    }
                )
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f"GitHub Trending fetch failed: {e}")
            return []

        repos = re.findall(
            r'<h2[^>]*>.*?<a[^>]*href="(/([^/]+)/([^"]+))"[^>]*>\s*(?:[^<]*/)?\s*([^<]*)',
            resp.text, re.DOTALL
        )
        seen = set()
        for full_path, owner, repo_name, _ in repos[:20]:
            if repo_name in seen:
                continue
            seen.add(repo_name)

            desc_match = re.search(
                rf'<p[^>]*>\s*({re.escape(repo_name)}[^<]*|[^<]{{10,200}})\s*</p>',
                resp.text, re.IGNORECASE
            )

            articles.append(Article(
                source_id=self.name,
                url=f"https://github.com{full_path}",
                title=f"{owner}/{repo_name}",
                summary=desc_match.group(1).strip() if desc_match else "",
                author=owner,
                published_at=datetime.now().isoformat(),
                language="en",
            ))

        return articles


register(GitHubTrendingCollector())
