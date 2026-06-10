import pytest


def test_cold_start_score_adds_score_field(test_db, test_config):
    from pipeline.ranking import _cold_start_score
    articles = [
        {"id": "a1", "title": "Test AI article", "source_id": "hackernews", "published_at": "2026-06-09T10:00:00"},
        {"id": "a2", "title": "Old article", "source_id": "reddit-ml", "published_at": "2026-06-05T10:00:00"},
    ]
    result = _cold_start_score(articles, test_config)
    for a in result:
        assert "score" in a
        assert isinstance(a["score"], float)
    # Newer article should score higher
    assert result[0]["id"] == "a1"


def test_cold_start_score_empty(test_db, test_config):
    from pipeline.ranking import _cold_start_score
    result = _cold_start_score([], test_config)
    assert result == []


def test_interest_bonus_no_topics():
    from pipeline.ranking import _calculate_interest_bonus
    art = {"title": "GPT-5 released", "summary": "OpenAI announced GPT-5"}
    result = _calculate_interest_bonus(art, {})
    assert result == 0.0


def test_interest_bonus_with_match():
    from pipeline.ranking import _calculate_interest_bonus
    art = {"title": "GPT-5 released with new features", "summary": "OpenAI announced GPT-5"}
    topic_weights = {"gpt-5": 1.0, "transformer": 1.0}
    result = _calculate_interest_bonus(art, topic_weights)
    assert result > 0.0


def test_score_articles_cold_start(test_db, test_config):
    from pipeline.ranking import score_articles
    articles = [
        {"id": "a1", "title": "Test", "source_id": "hackernews", "published_at": "2026-06-09T10:00:00"},
    ]
    result = score_articles(test_db, articles, test_config)
    assert len(result) == 1
    assert "score" in result[0]


def test_score_articles_with_feedback(test_db, test_config):
    """When feedback exists, blend should activate."""
    from pipeline.ranking import score_articles
    # Insert source and articles first to satisfy foreign key constraints
    test_db.execute(
        "INSERT OR IGNORE INTO sources (id, name, type, config) VALUES (?, ?, ?, ?)",
        ("hackernews", "HackerNews", "rss", "{}")
    )
    for i in range(20):
        test_db.execute(
            "INSERT OR IGNORE INTO articles (id, source_id, url, title, published_at) VALUES (?, ?, ?, ?, ?)",
            (f"art{i}", "hackernews", f"http://example.com/{i}", f"Article {i}", "2026-06-09T10:00:00")
        )
        test_db.execute(
            "INSERT INTO read_records (article_id, feedback, topics) VALUES (?, ?, ?)",
            (f"art{i}", "interested", "ai, llm")
        )
    test_db.commit()
    articles = [
        {"id": "a1", "title": "AI LLM research", "source_id": "hackernews", "published_at": "2026-06-09T10:00:00", "summary": "New AI research"},
    ]
    result = score_articles(test_db, articles, test_config)
    assert len(result) == 1
    assert "score" in result[0]


def test_get_user_topics(test_db):
    from pipeline.ranking import _get_user_topics
    # Initially empty
    topics = _get_user_topics(test_db)
    assert topics == set()


def test_exploration_floor(test_db, test_config):
    """Verify exploration floor marks correct number of articles."""
    from pipeline.ranking import _blend_score
    articles = [
        {"id": f"a{i}", "title": f"Article {i}", "source_id": "hackernews",
         "published_at": "2026-06-09T10:00:00", "summary": ""}
        for i in range(10)
    ]
    # Mock user_topics to return some topics
    import pipeline.ranking as ranking
    orig = ranking._get_user_topics
    try:
        ranking._get_user_topics = lambda conn: {"ai", "llm"}
        result = _blend_score(test_db, articles, test_config, blend=0.5)
        explore_count = sum(1 for a in result if a.get("_explore"))
        assert explore_count >= test_config.ranking.exploration_floor
        assert explore_count >= 2  # floor of 2
    finally:
        ranking._get_user_topics = orig
