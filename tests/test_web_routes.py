import pytest
import os, tempfile
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals, get_db
from web.routes import home, reader, search, concepts, review
from db.schema import init_db
from db.models import insert_article, set_full_text


@pytest.fixture
def client():
    tmp = os.path.join(tempfile.gettempdir(), "test_web_routes.db")
    conn = init_db(tmp)
    app = create_app()
    app.include_router(home.router)
    app.include_router(reader.router)
    app.include_router(search.router)
    app.include_router(concepts.router)
    app.include_router(review.router)
    set_globals(conn, None, None)
    yield TestClient(app)
    conn.close()
    try:
        os.unlink(tmp)
    except Exception:
        pass


class TestHomePage:
    def test_page_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "AI" in resp.text or "ai" in resp.text.lower()

    def test_no_db_still_renders(self):
        app = create_app()
        app.include_router(home.router)
        set_globals(None, None, None)
        client_tc = TestClient(app)
        resp = client_tc.get("/")
        assert resp.status_code == 200


class TestReaderPage:
    def test_nonexistent_article_returns_404(self, client):
        resp = client.get("/reader/nonexistent-id-12345")
        assert resp.status_code == 404

    def test_existing_article_renders(self, client):
        db = get_db()
        aid = insert_article(db, "hackernews", "https://example.com/reader-test", "Reader Test Article")
        set_full_text(db, aid, "Some full text content here")
        resp = client.get(f"/reader/{aid}")
        assert resp.status_code == 200

    def test_no_db_returns_404(self):
        app = create_app()
        app.include_router(reader.router)
        set_globals(None, None, None)
        client_tc = TestClient(app)
        resp = client_tc.get("/reader/some-id")
        assert resp.status_code == 404


class TestSearchPage:
    def test_page_loads_without_query(self, client):
        resp = client.get("/search")
        assert resp.status_code == 200

    def test_page_loads_with_query(self, client):
        resp = client.get("/search?q=machine+learning")
        assert resp.status_code == 200

    def test_no_db_renders_empty(self):
        app = create_app()
        app.include_router(search.router)
        set_globals(None, None, None)
        client_tc = TestClient(app)
        resp = client_tc.get("/search?q=test")
        assert resp.status_code == 200

    def test_query_with_results(self, client):
        db = get_db()
        aid = insert_article(db, "hackernews", "https://example.com/searchable", "Python Machine Learning Guide")
        set_full_text(db, aid, "Deep learning with transformers and neural networks")
        resp = client.get("/search?q=transformers")
        assert resp.status_code == 200


class TestConceptsPage:
    def test_page_loads(self, client):
        resp = client.get("/concepts")
        assert resp.status_code == 200

    def test_no_db_renders_empty(self):
        app = create_app()
        app.include_router(concepts.router)
        set_globals(None, None, None)
        client_tc = TestClient(app)
        resp = client_tc.get("/concepts")
        assert resp.status_code == 200


class TestReviewPage:
    def test_page_loads(self, client):
        resp = client.get("/review")
        assert resp.status_code == 200

    def test_no_db_renders_empty(self):
        app = create_app()
        app.include_router(review.router)
        set_globals(None, None, None)
        client_tc = TestClient(app)
        resp = client_tc.get("/review")
        assert resp.status_code == 200
