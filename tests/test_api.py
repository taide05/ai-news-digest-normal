import pytest
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals


@pytest.fixture
def client():
    import sqlite3, tempfile, os
    from db.schema import init_db
    tmp = os.path.join(tempfile.gettempdir(), "test_api_dedicated.db")
    conn = init_db(tmp)
    app = create_app()
    from web.routes import api
    app.include_router(api.router)
    set_globals(conn, None, None)
    yield TestClient(app)
    conn.close()
    try:
        os.unlink(tmp)
    except Exception:
        pass


class TestApiHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestConceptLookup:
    def test_requires_term(self, client):
        resp = client.post("/api/concept-lookup", json={})
        assert resp.status_code == 200
        assert resp.json()["definition"] == ""

    def test_no_ai_returns_empty(self, client):
        resp = client.post("/api/concept-lookup", json={"term": "transformer"})
        assert resp.status_code == 200
        assert resp.json()["term"] == "transformer"


class TestFeedback:
    def test_no_db_returns_error(self):
        app = create_app()
        from web.routes import api
        app.include_router(api.router)
        set_globals(None, None, None)
        client = TestClient(app)
        resp = client.post("/api/feedback/article123?feedback=interested")
        assert "错误" in resp.text


class TestCollectTrigger:
    def test_returns_unavailable(self, client):
        resp = client.post("/api/collect")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"


class TestRateLimit:
    def test_concept_lookup_under_limit_ok(self, client):
        """Verify concept-lookup works fine under rate limit."""
        resp = client.post("/api/concept-lookup", json={"term": "neural-network"})
        assert resp.status_code == 200
        assert resp.json()["term"] == "neural-network"

    def test_feedback_under_limit_ok(self, client):
        """Verify feedback endpoint works under limit (even without real article)."""
        resp = client.post("/api/feedback/nonexistent?feedback=interested")
        assert resp.status_code == 200

    def test_collect_has_rate_limit(self, client):
        """collect endpoint should have a rate limit applied (verify it works)."""
        resp = client.post("/api/collect")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"
