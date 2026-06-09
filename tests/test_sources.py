import pytest
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals
from web.routes import sources
import os, tempfile
from db.schema import init_db


@pytest.fixture
def client():
    tmp = os.path.join(tempfile.gettempdir(), "test_sources.db")
    conn = init_db(tmp)
    app = create_app()
    app.include_router(sources.router)
    set_globals(conn, None, None)
    yield TestClient(app)
    conn.close()
    try:
        os.unlink(tmp)
    except Exception:
        pass


class TestSourcesPage:
    def test_page_loads(self, client):
        resp = client.get("/sources")
        assert resp.status_code == 200
        assert "信息源管理" in resp.text

    def test_seeded_sources_present(self, client):
        resp = client.get("/sources")
        assert "arxiv-cs-ai" in resp.text
        assert "hackernews" in resp.text


class TestAddSource:
    def test_add_valid_source(self, client):
        resp = client.post("/api/sources", json={
            "id": "test-source", "name": "Test", "type": "rss",
            "config": '{"url": "https://example.com/rss"}'
        })
        assert resp.json()["status"] == "ok"

    def test_duplicate_id_rejected(self, client):
        client.post("/api/sources", json={
            "id": "dup-source", "name": "Test", "type": "rss",
            "config": '{"url": "https://example.com/rss"}'
        })
        resp = client.post("/api/sources", json={
            "id": "dup-source", "name": "Test2", "type": "rss",
            "config": '{"url": "https://example.com/rss"}'
        })
        assert resp.json()["status"] == "error"

    def test_invalid_json_config_rejected(self, client):
        resp = client.post("/api/sources", json={
            "id": "bad-config", "name": "Test", "type": "rss",
            "config": "not-valid-json"
        })
        assert resp.status_code == 400

    def test_missing_fields_rejected(self, client):
        resp = client.post("/api/sources", json={})
        assert resp.status_code == 400

    def test_non_alphanumeric_id_rejected(self, client):
        resp = client.post("/api/sources", json={
            "id": "bad id!", "name": "Test", "type": "rss",
            "config": '{"url": "https://example.com/rss"}'
        })
        assert resp.status_code == 400

    def test_malformed_json_rejected(self, client):
        resp = client.post("/api/sources", content="not json")
        assert resp.status_code == 400


class TestRemoveSource:
    def test_remove_existing(self, client):
        client.post("/api/sources", json={
            "id": "to-remove", "name": "X", "type": "rss", "config": '{"url":"x"}'
        })
        resp = client.delete("/api/sources/to-remove")
        assert resp.json()["status"] == "ok"

    def test_remove_nonexistent_is_ok(self, client):
        resp = client.delete("/api/sources/nonexistent-fake")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestToggleSource:
    def test_toggle_existing(self, client):
        resp = client.patch("/api/sources/arxiv-cs-ai", json={"enabled": False})
        assert resp.json()["status"] == "ok"

    def test_toggle_without_body(self, client):
        resp = client.patch("/api/sources/arxiv-cs-ai")
        assert resp.json()["status"] == "ok"
