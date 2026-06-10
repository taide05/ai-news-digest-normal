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
    tmp = os.path.join(tempfile.gettempdir(), "test_cross_compare.db")
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


def test_build_cross_comparison_prompt():
    from ai.analysis import build_cross_comparison_prompt
    articles = [
        {"title": "GPT-5 announced", "source_id": "hackernews",
         "insight": "OpenAI released GPT-5 with better benchmarks"},
        {"title": "GPT-5: A critical view", "source_id": "jiqizhixin",
         "insight": "GPT-5 benchmarks impressive but concerns remain"},
        {"title": "What GPT-5 means for startups", "source_id": "reddit-ml",
         "insight": "GPT-5 may lower barriers for AI startups"},
    ]
    system, user = build_cross_comparison_prompt(articles)
    assert "观点异同" in user
    assert "事实一致性" in user
    assert "信息源质量" in user
    assert "推荐阅读顺序" in user
    assert "GPT-5 announced" in user


def test_cross_compare_insufficient_articles(client):
    resp = client.post("/api/cross-compare/test-cl-small")
    assert resp.status_code == 200
    text = resp.text
    assert "不存在" in text or "3" in text


def test_cross_compare_invalid_cluster_id(client):
    long_id = "x" * 200
    resp = client.post(f"/api/cross-compare/{long_id}")
    assert resp.status_code == 200
    text = resp.text
    assert "无效" in text


def test_cross_compare_cached_response(client):
    from web.globals import get_db
    from db.models import cache_cross_analysis
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO clusters (id, label, digest_date) VALUES (?, ?, ?)",
        ("test-cl-cached", "test", "2026-06-09")
    )
    cache_cross_analysis(db, "test-cl-cached", "cross_comparison",
                         "预缓存的对比结果", ["a1", "a2", "a3"])
    db.commit()
    resp = client.post("/api/cross-compare/test-cl-cached")
    assert resp.status_code == 200
    text = resp.text
    assert "预缓存的对比结果" in text
