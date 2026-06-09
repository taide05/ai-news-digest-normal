import pytest
from unittest.mock import patch, MagicMock


def test_generate_weekly_review_markdown_format(test_db):
    """Verify generate_weekly_review wraps content in Markdown format."""
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

    # Mock AI client
    mock_ai = MagicMock()
    mock_ai.chat.return_value = ("本周你阅读了3篇文章。", 100)

    # Patch source modules since functions are locally imported in generate_weekly_review
    with patch('db.queries.get_weekly_review', return_value=None), \
         patch('db.queries.get_read_articles_with_insights', return_value=[
             {"title": "Test Article", "insight": "Something about AI"}
         ]), \
         patch('db.queries.get_feedback_articles', return_value=[]), \
         patch('db.queries.get_read_article_ids_since', return_value=["art1"]), \
         patch('db.queries.save_weekly_review'), \
         patch('db.models.get_concepts_list', return_value=[
             {"term": "transformer", "definition": "", "query_count": 5}
         ]), \
         patch('db.models.get_recommendations_gap', return_value=[]), \
         patch('ai.analysis.build_review_prompt', return_value=("system", "user")):

        result = generate_weekly_review(test_db, mock_ai, cfg)
        assert result is not None
        assert result["status"] == "ok"
        assert "# AI 资讯周刊" in result["content"]
        assert "## 本周概览" in result["content"]
        assert "## 本周热词" in result["content"]
        assert "## 推荐阅读" in result["content"]


def test_push_weekly_review_no_review_returns_false():
    """push_weekly_review returns False when no review exists in DB."""
    import asyncio
    from orchestrator import push_weekly_review
    from config import Config
    import tempfile
    import os
    from db.schema import init_db

    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    conn = init_db(db_path)
    cfg = Config(
        deepseek_api_key="",
        wecom_webhook_url="",
        exploration_rate=0.0,
        cluster_threshold=0.6,
        max_daily_articles=20,
        host="127.0.0.1",
        port=8765,
        full_text_retention_days=90,
        analysis_cache_retention_days=180,
    )
    try:
        result = asyncio.run(push_weekly_review(conn, cfg))
        assert result is False
    finally:
        conn.close()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
