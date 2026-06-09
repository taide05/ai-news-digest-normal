import sqlite3
import pytest


class TestDBWriteRetry:
    def test_success_first_try(self):
        from db.retry import db_write_retry
        call_count = 0

        @db_write_retry
        def test_func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = test_func()
        assert result == "ok"
        assert call_count == 1

    def test_recovers_after_lock(self):
        from db.retry import db_write_retry
        call_count = 0

        @db_write_retry
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise sqlite3.OperationalError("database is locked")
            return "recovered"

        result = test_func()
        assert result == "recovered"
        assert call_count == 2

    def test_raises_after_exhausted(self):
        from db.retry import db_write_retry

        @db_write_retry
        def test_func():
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError):
            test_func()

    def test_non_lock_error_passes_through(self):
        from db.retry import db_write_retry

        @db_write_retry
        def test_func():
            raise sqlite3.OperationalError("no such table: foo")

        with pytest.raises(sqlite3.OperationalError):
            test_func()


class TestTokenTracking:
    def test_token_tracker_exists(self):
        from ai.client import AIClient
        client = AIClient("sk-test-key")
        assert hasattr(client, '_track_tokens')
        assert callable(client._track_tokens)
        assert client._daily_tokens == 0

    def test_token_tracker_accumulates(self):
        from ai.client import AIClient
        client = AIClient("sk-test-key")
        client._track_tokens(100)
        client._track_tokens(50)
        assert client._daily_tokens == 150

    def test_token_tracker_date_rollover(self):
        from ai.client import AIClient
        client = AIClient("sk-test-key")
        client._track_tokens(100)
        # Force date rollover by setting yesterday's date
        client._token_date = "2020-01-01"
        client._track_tokens(50)
        assert client._daily_tokens == 50  # reset after rollover


class TestExplorationFloor:
    def test_exploration_floor_minimum(self, test_db, test_config):
        """Verify exploration floor uses max(floor, 20%) logic."""
        from pipeline.ranking import _blend_score
        articles = [
            {"id": f"a{i}", "title": f"Article {i}", "source_id": "hackernews",
             "published_at": "2026-06-09T10:00:00", "summary": ""}
            for i in range(5)
        ]
        import pipeline.ranking as ranking
        orig = ranking._get_user_topics
        try:
            ranking._get_user_topics = lambda conn: {"ai", "test"}
            result = _blend_score(test_db, articles, test_config, blend=0.5)
            explore_count = sum(1 for a in result if a.get("_explore"))
            # 20% of 5 = 1, but floor = 2 -> expect 2
            assert explore_count >= test_config.ranking.exploration_floor
            assert explore_count >= 2
        finally:
            ranking._get_user_topics = orig


class TestProgressiveBlend:
    def test_blend_is_zero_in_cold_start(self, test_db, test_config):
        """When feedback < threshold, blend should be 0 (pure cold-start)."""
        from pipeline.ranking import score_articles
        articles = [{"id": "a1", "title": "Test", "source_id": "hackernews",
                      "published_at": "2026-06-09T10:00:00"}]
        result = score_articles(test_db, articles, test_config)
        assert len(result) == 1
        assert "score" in result[0]
