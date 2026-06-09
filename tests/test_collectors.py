import pytest
from datetime import datetime, timedelta
from collectors.rss_reader import RSSCollector


@pytest.mark.asyncio
async def test_rss_collector_handles_bad_url():
    collector = RSSCollector("test-bad", "https://127.0.0.1:1/nonexistent", language="en")
    articles = await collector.fetch(datetime.now() - timedelta(days=1))
    assert articles == []


def test_rss_collector_attributes():
    collector = RSSCollector("test", "https://example.com/rss", language="zh")
    assert collector.name == "test"
    assert collector.language == "zh"
    assert collector.type == "rss"


from collectors.hackernews import HackerNewsCollector


class TestHackerNewsKeywordFilter:
    def setup_method(self):
        self.collector = HackerNewsCollector()

    def test_ai_title_matches(self):
        assert self.collector._is_ai_related("New LLM model released by OpenAI")
        assert self.collector._is_ai_related("Deep learning advances in 2026")

    def test_non_ai_title_rejected(self):
        assert not self.collector._is_ai_related("New JavaScript framework released")
        assert not self.collector._is_ai_related("")

    def test_keyword_case_insensitive(self):
        assert self.collector._is_ai_related("Building a RAG pipeline")
        assert self.collector._is_ai_related("New rag techniques")
