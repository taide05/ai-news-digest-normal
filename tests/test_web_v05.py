import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(test_db, test_config):
    from web.app import create_app
    from web.globals import set_globals
    set_globals(test_db, None, test_config)
    app = create_app()
    from web.routes import api, sources
    app.include_router(api.router)
    app.include_router(sources.router)
    return TestClient(app)


def test_list_source_candidates_empty(client):
    resp = client.get("/api/source-candidates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidates"] == []


def test_feedback_endpoint(test_db, client):
    # Insert a test article first (FK constraint)
    test_db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("test-fb-1", "hackernews", "https://example.com/fb1", "Test Article")
    )
    test_db.commit()
    resp = client.post("/api/feedback/test-fb-1?feedback=interested")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_source_candidates_page(client):
    resp = client.get("/sources/candidates")
    assert resp.status_code == 200
    assert "候选信息源" in resp.text


def test_verify_candidate_not_found(client):
    resp = client.post("/api/source-candidates/99999/verify")
    assert resp.status_code == 200  # should handle gracefully


def test_reject_candidate_not_found(client):
    resp = client.post("/api/source-candidates/99999/reject")
    assert resp.status_code == 200
