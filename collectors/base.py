from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    source_id: str
    url: str
    title: str
    summary: str = ""
    author: str | None = None
    published_at: str | None = None
    language: str = "en"
    content: str | None = None


class BaseCollector(ABC):
    name: str
    type: str  # 'rss' | 'api' | 'web'
    rate_limit: float = 0.5

    @abstractmethod
    async def fetch(self, since: datetime) -> list[Article]:
        ...
