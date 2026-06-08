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
