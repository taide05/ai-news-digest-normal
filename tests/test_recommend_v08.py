def test_recommendations_cluster_empty(test_db):
    from db.models import get_recommendations_cluster
    result = get_recommendations_cluster(test_db, 2)
    assert result == []


def test_recommendations_cluster_finds_recent_topics(test_db):
    from db.models import (get_recommendations_cluster, insert_article,
                           get_or_create_concept, link_article_concept, record_read)
    from db.url_utils import make_article_id

    insert_article(test_db, "hackernews", "https://example.com/c1", "Cluster Article 1", commit=False)
    insert_article(test_db, "hackernews", "https://example.com/c2", "Cluster Target", commit=False)
    aid1 = make_article_id("hackernews", "https://example.com/c1")
    aid2 = make_article_id("hackernews", "https://example.com/c2")

    cid = get_or_create_concept(test_db, "transformer", commit=False)
    link_article_concept(test_db, aid1, cid, commit=False)
    link_article_concept(test_db, aid2, cid, commit=False)
    record_read(test_db, aid1, commit=True)

    result = get_recommendations_cluster(test_db, 2)
    assert len(result) == 1
    assert result[0]["id"] == aid2
    assert "近期关注" in result[0]["reason"]
    assert "transformer" in result[0]["reason"]


def test_recommendations_cluster_excludes_read(test_db):
    from db.models import (get_recommendations_cluster, insert_article,
                           get_or_create_concept, link_article_concept, record_read)
    from db.url_utils import make_article_id

    insert_article(test_db, "hackernews", "https://example.com/c3", "Read Article", commit=False)
    insert_article(test_db, "hackernews", "https://example.com/c4", "Also Read", commit=False)
    aid1 = make_article_id("hackernews", "https://example.com/c3")
    aid2 = make_article_id("hackernews", "https://example.com/c4")

    cid = get_or_create_concept(test_db, "rlhf", commit=False)
    link_article_concept(test_db, aid1, cid, commit=False)
    link_article_concept(test_db, aid2, cid, commit=False)
    record_read(test_db, aid1, commit=True)
    record_read(test_db, aid2, commit=True)

    result = get_recommendations_cluster(test_db, 2)
    assert result == []


def test_get_recent_articles(test_db):
    from db.models import get_recent_articles
    test_db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("ra-1", "hackernews", "https://example.com/ra1", "Recent 1")
    )
    test_db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("ra-2", "jiqizhixin", "https://example.com/ra2", "Recent 2")
    )
    test_db.commit()
    result = get_recent_articles(test_db, "ra-1", exclude_read=False, limit=1)
    assert len(result) == 1
    assert result[0]["id"] == "ra-2"


import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals
from web.routes import api
from db.schema import init_db


@pytest.fixture
def client():
    tmp = os.path.join(tempfile.gettempdir(), "test_recommend_v08_api.db")
    conn = init_db(tmp)
    app = create_app()
    app.include_router(api.router)
    set_globals(conn, None, None)
    yield TestClient(app)
    conn.close()
    try:
        os.unlink(tmp)
    except Exception:
        pass


def test_recommend_endpoint_no_data_returns_empty(client):
    resp = client.get("/api/recommend/nonexistent")
    assert resp.status_code == 200
    assert resp.text == ""


def test_recommend_endpoint_fallback_to_recent(client):
    from web.globals import get_db
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("rec-fb-1", "hackernews", "https://example.com/fb1", "Fallback Article")
    )
    db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("rec-fb-2", "jiqizhixin", "https://example.com/fb2", "Current Article")
    )
    db.commit()
    resp = client.get("/api/recommend/rec-fb-2")
    assert resp.status_code == 200
    assert "Fallback Article" in resp.text
    assert "热门文章" in resp.text
