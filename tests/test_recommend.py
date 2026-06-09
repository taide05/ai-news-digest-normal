import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals
from web.routes import api
from db.schema import init_db


# ── Model query tests ──────────────────────────────────────────────────

def test_recommendations_empty(test_db):
    from db.models import get_recommendations_interest, get_recommendations_gap
    assert get_recommendations_interest(test_db, "nonexistent", 2) == []
    assert get_recommendations_gap(test_db, 2) == []


def test_recommendations_interest_finds_similar(test_db):
    from db.models import (get_recommendations_interest,
                           get_or_create_concept, link_article_concept,
                           insert_article)
    from db.url_utils import make_article_id
    insert_article(test_db, "hackernews", "https://example.com/r1", "Article 1", commit=False)
    insert_article(test_db, "hackernews", "https://example.com/r2", "Article 2", commit=False)
    aid1 = make_article_id("hackernews", "https://example.com/r1")
    aid2 = make_article_id("hackernews", "https://example.com/r2")
    cid = get_or_create_concept(test_db, "transformer", commit=False)
    link_article_concept(test_db, aid1, cid, commit=False)
    link_article_concept(test_db, aid2, cid, commit=False)
    test_db.commit()
    results = get_recommendations_interest(test_db, aid1, 2)
    assert len(results) == 1
    assert results[0]["id"] == aid2


def test_recommendations_excludes_read(test_db):
    from db.models import (get_recommendations_interest, insert_article, record_read,
                           get_or_create_concept, link_article_concept)
    from db.url_utils import make_article_id
    insert_article(test_db, "hackernews", "https://example.com/r3", "Article 3", commit=False)
    insert_article(test_db, "hackernews", "https://example.com/r4", "Article 4", commit=False)
    aid3 = make_article_id("hackernews", "https://example.com/r3")
    aid4 = make_article_id("hackernews", "https://example.com/r4")
    cid = get_or_create_concept(test_db, "rlhf", commit=False)
    link_article_concept(test_db, aid3, cid, commit=False)
    link_article_concept(test_db, aid4, cid, commit=False)
    record_read(test_db, aid4, commit=True)
    results = get_recommendations_interest(test_db, aid3, 2)
    assert len(results) == 0  # aid4 excluded because already read


# ── API endpoint test ──────────────────────────────────────────────────

@pytest.fixture
def client():
    tmp = os.path.join(tempfile.gettempdir(), "test_recommend_api.db")
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


def test_recommend_endpoint_no_data(client):
    resp = client.get("/api/recommend/nonexistent")
    assert resp.status_code == 200
    assert resp.text == ""


def test_recommend_endpoint_renders_html(client):
    from web.globals import get_db
    from db.models import get_or_create_concept, link_article_concept
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("rec-src-1", "hackernews", "https://example.com/rec1", "Recommendation Source")
    )
    db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("rec-tgt-1", "jiqizhixin", "https://example.com/rec2", "Recommendation Target")
    )
    cid = get_or_create_concept(db, "transformer", commit=False)
    link_article_concept(db, "rec-src-1", cid, commit=False)
    link_article_concept(db, "rec-tgt-1", cid, commit=False)
    db.commit()
    resp = client.get("/api/recommend/rec-src-1")
    assert resp.status_code == 200
    assert "Recommendation Target" in resp.text
    assert "推荐阅读" in resp.text
