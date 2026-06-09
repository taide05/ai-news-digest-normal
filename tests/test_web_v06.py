import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals
from web.routes import home, reader
from db.schema import init_db
from db.models import insert_article, set_full_text


@pytest.fixture
def client():
    tmp = os.path.join(tempfile.gettempdir(), "test_web_v06.db")
    conn = init_db(tmp)
    app = create_app()
    app.include_router(home.router)
    app.include_router(reader.router)
    set_globals(conn, None, None)
    yield TestClient(app)
    conn.close()
    try:
        os.unlink(tmp)
    except Exception:
        pass


def test_reader_page_has_collapsible_section(client):
    from web.globals import get_db
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("v06-test-1", "hackernews", "https://example.com/v06", "Test V06 Article")
    )
    db.execute(
        "INSERT OR IGNORE INTO clusters (id, label, digest_date) VALUES (?, ?, ?)",
        ("v06-cluster", "Test Cluster", "2026-06-09")
    )
    db.execute(
        "INSERT OR IGNORE INTO cluster_articles (cluster_id, article_id) VALUES (?, ?)",
        ("v06-cluster", "v06-test-1")
    )
    db.commit()
    resp = client.get("/reader/v06-test-1")
    assert resp.status_code == 200
    assert "这意味着什么" in resp.text


def test_reader_no_cross_compare_when_few_articles(client):
    from web.globals import get_db
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("v06-solo", "hackernews", "https://example.com/solo", "Solo Article")
    )
    db.execute(
        "INSERT OR IGNORE INTO clusters (id, label, digest_date) VALUES (?, ?, ?)",
        ("v06-cluster-solo", "Solo Cluster", "2026-06-09")
    )
    db.execute(
        "INSERT OR IGNORE INTO cluster_articles (cluster_id, article_id) VALUES (?, ?)",
        ("v06-cluster-solo", "v06-solo")
    )
    db.commit()
    resp = client.get("/reader/v06-solo")
    assert resp.status_code == 200
    assert "对比同话题" not in resp.text


def test_reader_shows_cross_compare_when_enough_articles(client):
    from web.globals import get_db
    db = get_db()
    for i in range(3):
        aid = f"v06-multi-{i}"
        db.execute(
            "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
            (aid, "hackernews", f"https://example.com/multi-{i}", f"Article {i}")
        )
    db.execute(
        "INSERT OR IGNORE INTO clusters (id, label, digest_date) VALUES (?, ?, ?)",
        ("v06-cluster-multi", "Multi Cluster", "2026-06-09")
    )
    for i in range(3):
        db.execute(
            "INSERT OR IGNORE INTO cluster_articles (cluster_id, article_id) VALUES (?, ?)",
            ("v06-cluster-multi", f"v06-multi-{i}")
        )
    db.commit()
    resp = client.get("/reader/v06-multi-0")
    assert resp.status_code == 200
    assert "对比同话题 3 篇文章" in resp.text


def test_home_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
