import pytest
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals, get_db
from web.routes import export
import os, tempfile
from db.schema import init_db
from db.models import insert_article, set_full_text, cache_analysis


@pytest.fixture
def client():
    tmp = os.path.join(tempfile.gettempdir(), "test_export.db")
    conn = init_db(tmp)
    app = create_app()
    app.include_router(export.router)
    set_globals(conn, None, None)
    yield TestClient(app)
    conn.close()
    try:
        os.unlink(tmp)
    except Exception:
        pass


class TestExportArticle:
    def test_nonexistent_article_returns_404(self, client):
        resp = client.get("/api/export/article/nonexistent123")
        assert resp.status_code == 404

    def test_existing_article_returns_markdown(self, client):
        db = get_db()
        aid = insert_article(db, "hackernews", "https://example.com/test-export", "Test Export Article")
        set_full_text(db, aid, "Article body content")
        cache_analysis(db, aid, "core_insight", "This is the insight")
        cache_analysis(db, aid, "what_it_means", "This means something")

        resp = client.get(f"/api/export/article/{aid}")
        assert resp.status_code == 200
        assert "markdown" in resp.headers.get("content-type", "")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "Test Export Article" in resp.text
        assert "This is the insight" in resp.text


class TestExportReview:
    def test_no_review_returns_404(self, client):
        resp = client.get("/api/export/review")
        assert resp.status_code == 404

    def test_no_db_returns_500(self):
        app = create_app()
        app.include_router(export.router)
        set_globals(None, None, None)
        client = TestClient(app)
        resp = client.get("/api/export/review")
        assert resp.status_code == 500

    def test_no_db_article_returns_500(self):
        app = create_app()
        app.include_router(export.router)
        set_globals(None, None, None)
        client = TestClient(app)
        resp = client.get("/api/export/article/some-id")
        assert resp.status_code == 500
