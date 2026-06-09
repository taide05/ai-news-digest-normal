import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals
from web.routes import graph
from db.schema import init_db


def test_get_graph_data_empty(test_db):
    from db.models import get_graph_data
    rows = get_graph_data(test_db, "today")
    assert rows == []


def test_get_graph_data_with_data(test_db):
    from db.models import get_graph_data, get_or_create_concept, link_article_concept
    test_db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("g-art-1", "hackernews", "https://example.com/g1", "Graph Article")
    )
    test_db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("g-art-2", "jiqizhixin", "https://example.com/g2", "Graph Article 2")
    )
    cid = get_or_create_concept(test_db, "transformer", commit=False)
    link_article_concept(test_db, "g-art-1", cid, commit=False)
    link_article_concept(test_db, "g-art-2", cid, commit=False)
    test_db.commit()
    rows = get_graph_data(test_db, "today")
    assert len(rows) == 2
    assert rows[0]["concept"] == "transformer"


@pytest.fixture
def client():
    tmp = os.path.join(tempfile.gettempdir(), "test_graph_page.db")
    conn = init_db(tmp)
    app = create_app()
    app.include_router(graph.router)
    set_globals(conn, None, None)
    yield TestClient(app)
    conn.close()
    try:
        os.unlink(tmp)
    except Exception:
        pass


def test_graph_page_loads_empty(client):
    resp = client.get("/graph")
    assert resp.status_code == 200
    assert "还没有" in resp.text


def test_graph_page_loads_today(client):
    resp = client.get("/graph?period=today")
    assert resp.status_code == 200


def test_graph_page_loads_week(client):
    resp = client.get("/graph?period=week")
    assert resp.status_code == 200
