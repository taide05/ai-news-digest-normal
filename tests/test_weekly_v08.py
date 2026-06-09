def test_weekly_hot_concepts(test_db):
    from db.models import get_weekly_hot_concepts
    from datetime import date
    today = date.today().isoformat()
    test_db.execute(
        "INSERT OR IGNORE INTO concepts (term, query_count, last_seen) VALUES (?, ?, ?)",
        ("transformer", 15, today)
    )
    test_db.execute(
        "INSERT OR IGNORE INTO concepts (term, query_count, last_seen) VALUES (?, ?, ?)",
        ("agent", 12, "2020-01-01")
    )
    test_db.commit()
    hot = get_weekly_hot_concepts(test_db, today)
    assert len(hot) == 1
    assert hot[0]["term"] == "transformer"


def test_weekly_growing_concepts(test_db):
    from db.models import get_weekly_growing_concepts
    from datetime import date
    today = date.today().isoformat()
    test_db.execute(
        "INSERT OR IGNORE INTO concepts (term, query_count, first_seen, definition) VALUES (?, ?, ?, ?)",
        ("tool-use", 5, today, "")
    )
    test_db.commit()
    growing = get_weekly_growing_concepts(test_db, today)
    assert len(growing) == 1
    assert growing[0]["term"] == "tool-use"


def test_weekly_date_format_validation():
    import pytest
    from db.models import _get_weekly_concepts_by_date
    with pytest.raises(AssertionError):
        _get_weekly_concepts_by_date(None, "bad", "invalid_column", 5)
    with pytest.raises(AssertionError):
        _get_weekly_concepts_by_date(None, "bad", "last_seen", 5)


def test_weekly_stats_empty(test_db):
    from db.models import get_weekly_hot_concepts, get_weekly_growing_concepts
    assert get_weekly_hot_concepts(test_db, "2099-01-01") == []
    assert get_weekly_growing_concepts(test_db, "2099-01-01") == []


import pytest
from unittest.mock import patch, MagicMock


def test_generate_weekly_review_with_stats(test_db):
    from orchestrator import generate_weekly_review
    from config import Config

    cfg = Config(
        deepseek_api_key="sk-test",
        wecom_webhook_url="",
        exploration_rate=0.0,
        cluster_threshold=0.6,
        max_daily_articles=20,
        host="127.0.0.1",
        port=8765,
        full_text_retention_days=90,
        analysis_cache_retention_days=180,
    )

    mock_ai = MagicMock()
    mock_ai.chat.return_value = ("本周你阅读了文章。", 100)

    with patch('db.queries.get_weekly_review', return_value=None), \
         patch('utils.get_week_bounds', return_value=("2026-06-08", "2026-06-14")), \
         patch('db.queries.get_read_articles_with_insights', return_value=[
             {"title": "Test", "insight": "AI stuff"}
         ]), \
         patch('db.models.get_concepts_list', return_value=[
             {"term": "transformer", "definition": "", "query_count": 5}
         ]), \
         patch('db.queries.get_feedback_articles', return_value=[]), \
         patch('ai.analysis.build_review_prompt', return_value=("system", "user")), \
         patch('db.queries.get_read_article_ids_since', return_value=["art1"]), \
         patch('db.models.get_weekly_hot_concepts', return_value=[
             {"term": "agent", "count": 12}
         ]), \
         patch('db.models.get_weekly_growing_concepts', return_value=[
             {"term": "tool-use", "count": 5}
         ]), \
         patch('db.models.get_recommendations_cluster', return_value=[]), \
         patch('db.queries.save_weekly_review'):

        result = generate_weekly_review(test_db, mock_ai, cfg)
        assert result is not None
        assert result["status"] == "ok"
        assert "## 新晋概念" in result["content"]
        assert "agent (12次)" in result["content"]
        assert "tool-use (5次)" in result["content"]
