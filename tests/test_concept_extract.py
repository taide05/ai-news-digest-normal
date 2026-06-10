import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals
from web.routes import api
from db.schema import init_db


# ── Prompt format tests ──────────────────────────────────────────────

def test_concept_extraction_prompt_format():
    from ai.analysis import build_concept_extraction_prompt
    system, user = build_concept_extraction_prompt("Transformer models use attention mechanisms.")
    assert "JSON" in system
    assert "concepts" in system
    assert "Transformer" in user


def test_concept_extraction_prompt_long_text_truncated():
    from ai.analysis import build_concept_extraction_prompt
    long_text = "AI " * 5000
    system, user = build_concept_extraction_prompt(long_text)
    assert len(user) < 12000


# ── API endpoint tests ───────────────────────────────────────────────

@pytest.fixture
def client():
    tmp = os.path.join(tempfile.gettempdir(), "test_concept_extract.db")
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


def test_auto_extract_concepts_no_ai_returns_empty(client):
    from web.globals import get_db
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title, full_text) VALUES (?, ?, ?, ?, ?)",
        ("test-extract-1", "hackernews", "https://example.com/ec1", "Test Article",
         "Transformer models revolutionized NLP with self-attention mechanisms.")
    )
    db.commit()
    resp = client.get("/api/auto-extract-concepts/test-extract-1")
    assert resp.status_code == 200
    assert resp.text == ""  # No AI, returns empty HTML


def test_auto_extract_concepts_cached_response(client):
    from web.globals import get_db
    from db.models import cache_analysis
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title, full_text) VALUES (?, ?, ?, ?, ?)",
        ("test-extract-2", "hackernews", "https://example.com/ec2", "Cached Article",
         "Some content about reinforcement learning.")
    )
    cache_analysis(db, "test-extract-2", "concepts", '["RL","PPO"]')
    db.commit()
    resp = client.get("/api/auto-extract-concepts/test-extract-2")
    assert resp.status_code == 200
    assert "RL" in resp.text
    assert "PPO" in resp.text
