import json
import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals
from web.routes import graph
from db.schema import init_db


def test_save_and_get_graph_snapshot(test_db):
    from db.models import save_graph_snapshot, get_graph_snapshot
    data = {"nodes": [{"id": "a", "label": "Test"}], "edges": []}
    save_graph_snapshot(test_db, "2026-06-09", "today", data)
    result = get_graph_snapshot(test_db, "2026-06-09", "today")
    assert result is not None
    assert result["nodes"][0]["label"] == "Test"


def test_snapshot_upsert(test_db):
    from db.models import save_graph_snapshot, get_graph_snapshot
    data1 = {"nodes": [{"id": "a", "label": "V1"}], "edges": []}
    data2 = {"nodes": [{"id": "a", "label": "V2"}], "edges": []}
    save_graph_snapshot(test_db, "2026-06-09", "today", data1)
    save_graph_snapshot(test_db, "2026-06-09", "today", data2)
    result = get_graph_snapshot(test_db, "2026-06-09", "today")
    assert result["nodes"][0]["label"] == "V2"


def test_get_snapshot_dates(test_db):
    from db.models import save_graph_snapshot, get_snapshot_dates
    save_graph_snapshot(test_db, "2026-06-09", "today", {"nodes": [], "edges": []})
    save_graph_snapshot(test_db, "2026-06-08", "today", {"nodes": [], "edges": []})
    dates = get_snapshot_dates(test_db)
    assert len(dates) == 2
    assert dates[0] == "2026-06-09"


def test_get_snapshot_nonexistent(test_db):
    from db.models import get_graph_snapshot
    result = get_graph_snapshot(test_db, "2099-01-01", "today")
    assert result is None


@pytest.fixture
def client():
    tmp = os.path.join(tempfile.gettempdir(), "test_graph_v08_page.db")
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


def test_graph_page_compare_param(client):
    resp = client.get("/graph?period=today&compare=2026-06-01")
    assert resp.status_code == 200


def test_graph_page_no_history_has_no_compare_select(client):
    resp = client.get("/graph")
    assert resp.status_code == 200
    assert "compare-select" not in resp.text


def test_graph_page_with_snapshots_shows_dates(client):
    from web.globals import get_db
    from db.models import save_graph_snapshot
    db = get_db()
    save_graph_snapshot(db, "2026-06-08", "today", {"nodes": [], "edges": []})
    save_graph_snapshot(db, "2026-06-09", "today", {"nodes": [], "edges": []})
    db.commit()
    resp = client.get("/graph")
    assert resp.status_code == 200
    assert "compare-select" in resp.text
    assert "2026-06-09" in resp.text
