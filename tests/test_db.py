import pytest
import sqlite3
import tempfile
import os
from db.schema import init_db


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        conn = init_db(path)
        yield conn
        conn.close()


def test_sources_seeded_on_first_init(db):
    rows = db.execute("SELECT id, name, type FROM sources ORDER BY id").fetchall()
    assert len(rows) == 5
    assert rows[0][0] == "arxiv-cs-ai"


def test_sources_not_duplicated_on_reinit(db):
    db.execute("INSERT INTO sources (id, name, type, config) VALUES ('test', 'Test', 'rss', '{}')")
    db.commit()
    # Re-init same DB path — verify seed doesn't re-insert
    db_path = db.execute("PRAGMA database_list").fetchone()[2]
    conn2 = init_db(db_path)
    rows = conn2.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    assert rows == 6  # 5 default + 1 test, not 10
    conn2.close()


def test_articles_unique_constraint(db):
    db.execute(
        "INSERT INTO articles (id, source_id, url, title, language) VALUES ('a1', 'arxiv-cs-ai', 'http://example.com/1', 'Test', 'en')"
    )
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO articles (id, source_id, url, title, language) VALUES ('a2', 'arxiv-cs-ai', 'http://example.com/1', 'Test2', 'en')"
        )


from db.models import (
    get_article, get_or_create_concept, link_article_concept,
    get_concepts_list, cache_analysis, get_cached_analysis,
    save_weekly_review, get_weekly_review, search_articles, cleanup_old_data,
)


class TestConceptOperations:
    def test_create_and_get_concept(self, db):
        cid = get_or_create_concept(db, "transformer", "A neural network architecture")
        assert cid > 0
        concepts = get_concepts_list(db)
        assert any(c["term"] == "transformer" for c in concepts)

    def test_repeat_query_increments_count(self, db):
        get_or_create_concept(db, "rag2", "Retrieval augmented generation")
        cid2 = get_or_create_concept(db, "rag2", "Updated definition")
        concepts = get_concepts_list(db)
        rag = next(c for c in concepts if c["term"] == "rag2")
        assert rag["query_count"] >= 2


class TestAnalysisCache:
    def test_cache_and_retrieve(self, db):
        from db.models import insert_article
        aid = insert_article(db, "hackernews", "https://x.com/cache-test", "Cache Test")
        cache_analysis(db, aid, "core_insight", "This is the insight")
        cached = get_cached_analysis(db, aid, "core_insight")
        assert cached == "This is the insight"

    def test_cache_miss_returns_none(self, db):
        assert get_cached_analysis(db, "nonexistent", "core_insight") is None


class TestWeeklyReview:
    def test_save_and_get_review(self, db):
        save_weekly_review(db, "2026-06-01", "2026-06-07", "Weekly content", ["id1", "id2"])
        review = get_weekly_review(db, "2026-06-01")
        assert review is not None
        assert review["content"] == "Weekly content"


class TestSearch:
    def test_search_returns_results(self, db):
        from db.models import insert_article, set_full_text
        aid = insert_article(db, "hackernews", "https://x.com/search-test", "Python ML Guide")
        set_full_text(db, aid, "A comprehensive guide to machine learning with Python")
        results = search_articles(db, "machine learning")
        assert len(results) > 0


def test_fts5_trigger_insert(db):
    db.execute(
        "INSERT INTO articles (id, source_id, url, title, full_text, language) VALUES ('a1', 'arxiv-cs-ai', 'http://x.com/1', 'Hello World', 'some content here', 'en')"
    )
    db.commit()
    rows = db.execute("SELECT title FROM articles_fts WHERE articles_fts MATCH 'hello'").fetchall()
    assert len(rows) >= 1
