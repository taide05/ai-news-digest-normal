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


def test_fts5_trigger_insert(db):
    db.execute(
        "INSERT INTO articles (id, source_id, url, title, full_text, language) VALUES ('a1', 'arxiv-cs-ai', 'http://x.com/1', 'Hello World', 'some content here', 'en')"
    )
    db.commit()
    rows = db.execute("SELECT title FROM articles_fts WHERE articles_fts MATCH 'hello'").fetchall()
    assert len(rows) >= 1
