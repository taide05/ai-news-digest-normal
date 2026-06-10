import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(test_db, test_config):
    from web.app import create_app
    from web.globals import set_globals
    set_globals(test_db, None, test_config)
    app = create_app()
    from web.routes import concepts
    app.include_router(concepts.router)
    return TestClient(app)


def test_concept_detail_route_returns_html(client, test_db):
    """/concepts/<label> returns HTML page."""
    from db.models import save_concept_nodes
    today = "2026-06-10"
    nodes = [{"type": "concept", "label": "Transformer", "weight": 3.0}]
    save_concept_nodes(test_db, today, nodes)

    response = client.get("/concepts/Transformer")
    assert response.status_code == 200
    assert "Transformer" in response.text
    assert "concept-detail" in response.text


def test_concept_detail_unknown_label(client):
    """Unknown concept still renders page gracefully."""
    response = client.get("/concepts/NonexistentConcept")
    assert response.status_code == 200
    assert "NonexistentConcept" in response.text


def test_concept_detail_has_back_link(client, test_db):
    from db.models import save_concept_nodes
    save_concept_nodes(test_db, "2026-06-10",
                       [{"type": "concept", "label": "Test", "weight": 1.0}])

    response = client.get("/concepts/Test")
    assert 'href="/concepts"' in response.text
