from datetime import datetime
import logging
import httpx
import xml.etree.ElementTree as ET
from .base import BaseCollector, Article
from .registry import register

logger = logging.getLogger(__name__)
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivCollector(BaseCollector):
    name = "arxiv-cs-ai"
    type = "api"
    rate_limit = 3.0

    def __init__(self):
        self.endpoint = "https://export.arxiv.org/api/query"
        self.categories = ["cs.AI", "cs.CL", "cs.LG"]
        self.max_results = 50

    async def fetch(self, since: datetime) -> list[Article]:
        articles = []
        cat_query = "+OR+".join(f"cat:{c}" for c in self.categories)
        url = f"{self.endpoint}?search_query={cat_query}&start=0&max_results={self.max_results}&sortBy=submittedDate&sortOrder=descending"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={"User-Agent": "ai-news-digest/0.1"})
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f"arXiv fetch failed: {e}")
            return []

        root = ET.fromstring(resp.text)
        for entry in root.findall("atom:entry", ARXIV_NS):
            title_el = entry.find("atom:title", ARXIV_NS)
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            title = " ".join(title.split())

            link_el = entry.find("atom:id", ARXIV_NS)
            url = link_el.text.strip() if link_el is not None and link_el.text else ""

            summary_el = entry.find("atom:summary", ARXIV_NS)
            summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""

            published_el = entry.find("atom:published", ARXIV_NS)
            published_str = published_el.text.strip() if published_el is not None and published_el.text else ""
            pub_dt = None
            try:
                pub_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00")).replace(tzinfo=None)
                if pub_dt < since:
                    continue
            except ValueError:
                pass

            authors = []
            for author_el in entry.findall("atom:author", ARXIV_NS):
                name_el = author_el.find("atom:name", ARXIV_NS)
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())
            author_str = ", ".join(authors[:3])

            articles.append(Article(
                source_id=self.name,
                url=url,
                title=title,
                summary=summary,
                author=author_str or None,
                published_at=pub_dt.isoformat() if pub_dt else None,
                language="en",
                content=None,
            ))

        return articles


register(ArxivCollector())
