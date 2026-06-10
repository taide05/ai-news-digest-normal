import pytest
from db.models import (
    save_concept_nodes, get_concept_nodes_by_date,
    get_concept_node_history, get_distinct_concept_labels,
    backfill_concept_nodes_from_snapshots, prune_stale_concepts
)


def test_save_and_get_concept_nodes(test_db):
    """Save concept nodes and retrieve them by date."""
    nodes = [
        {"type": "concept", "label": "Transformer", "weight": 5.0, "query_count": 5},
        {"type": "concept", "label": "RLHF", "weight": 3.0, "query_count": 3},
        {"type": "article", "label": "Some Article"},  # should be skipped
    ]
    save_concept_nodes(test_db, "2026-06-10", nodes)

    results = get_concept_nodes_by_date(test_db, "2026-06-10")
    assert len(results) == 2
    labels = {r["label"] for r in results}
    assert labels == {"Transformer", "RLHF"}


def test_save_concept_nodes_upsert(test_db):
    """Second save for same label+date updates weight and article_count."""
    nodes = [
        {"type": "concept", "label": "Transformer", "weight": 2.0, "query_count": 2},
    ]
    save_concept_nodes(test_db, "2026-06-10", nodes)
    # Save again with different weight
    save_concept_nodes(test_db, "2026-06-10", nodes)

    results = get_concept_nodes_by_date(test_db, "2026-06-10")
    assert len(results) == 1
    assert results[0]["article_count"] == 2  # incremented


def test_get_concept_node_history(test_db):
    """History returns daily snapshots for a concept."""
    for day in range(3):
        date = f"2026-06-{10 + day:02d}"
        nodes = [{"type": "concept", "label": "Transformer", "weight": 2.0 + day}]
        save_concept_nodes(test_db, date, nodes)

    history = get_concept_node_history(test_db, "Transformer", days=30)
    assert len(history) == 3
    assert history[0]["weight"] == 2.0
    assert history[-1]["weight"] == 4.0


def test_get_distinct_concept_labels(test_db):
    nodes_a = [{"type": "concept", "label": "Alpha", "weight": 1.0}]
    nodes_b = [{"type": "concept", "label": "Beta", "weight": 1.0}]
    save_concept_nodes(test_db, "2026-06-10", nodes_a)
    save_concept_nodes(test_db, "2026-06-10", nodes_b)

    labels = get_distinct_concept_labels(test_db)
    assert "Alpha" in labels and "Beta" in labels


def test_backfill_skips_when_populated(test_db):
    """backfill returns 0 when concept_nodes already has data."""
    nodes = [{"type": "concept", "label": "Test", "weight": 1.0}]
    save_concept_nodes(test_db, "2026-06-10", nodes)

    count = backfill_concept_nodes_from_snapshots(test_db)
    assert count == 0


def test_prune_stale_concepts(test_db):
    """Pruning removes old declining low-weight concepts."""
    conn = test_db
    conn.execute(
        "INSERT INTO concept_nodes (concept_label, weight, article_count, "
        "first_seen_date, last_seen_date, snap_date, lifecycle_state) "
        "VALUES ('old_concept', 0.5, 1, '2026-01-01', '2026-01-01', "
        "date('now', '-100 days'), 'declining')"
    )
    conn.commit()

    prune_stale_concepts(test_db, retention_days=90, weight_threshold=1.0)

    history = get_concept_node_history(test_db, "old_concept", days=200)
    assert len(history) == 0  # pruned
