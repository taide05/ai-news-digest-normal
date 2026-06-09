import pytest
import asyncio


def test_collect_all_returns_list(test_db, test_config):
    from orchestrator import collect_all
    articles = asyncio.run(collect_all(test_db, test_config))
    assert isinstance(articles, list)


def test_dedup_articles_empty():
    from orchestrator import dedup_articles
    result = dedup_articles(None, [])
    assert result == []


def test_dedup_articles_preserves_unique(test_db):
    from orchestrator import dedup_articles
    articles = [
        {"id": "a1", "title": "Unique Article One"},
        {"id": "a2", "title": "Different Title Two"},
    ]
    result = dedup_articles(test_db, articles)
    assert len(result) == 2


def test_rank_articles_adds_score(test_db, test_config):
    from orchestrator import rank_articles
    articles = [{"id": "test1", "title": "Test"}]
    result = rank_articles(test_db, articles, test_config)
    assert len(result) == 1
    assert "score" in result[0]


def test_cluster_articles_empty(test_db, test_config):
    from orchestrator import cluster_articles
    result = cluster_articles(test_db, [], test_config)
    assert result == []


def test_run_full_pipeline_integration(test_db, test_config):
    from orchestrator import run_full_pipeline
    count = asyncio.run(run_full_pipeline(test_db, None, test_config))
    assert isinstance(count, int)


def test_generate_weekly_review_no_data(test_db, test_config):
    from orchestrator import generate_weekly_review
    result = generate_weekly_review(test_db, None, test_config)
    # No AI client -> should return None since no content can be generated
    assert result is None


def test_push_weekly_review_no_review(test_db, test_config):
    from orchestrator import push_weekly_review
    result = asyncio.run(push_weekly_review(test_db, test_config))
    assert result is False  # no review exists
