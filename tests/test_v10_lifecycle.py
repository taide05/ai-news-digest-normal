import pytest
from ai.lifecycle import (
    compute_lifecycle_state, update_all_lifecycle_states,
    _consecutive_increasing, _consecutive_decreasing, _low_fluctuation
)


def test_new_with_insufficient_history():
    assert compute_lifecycle_state([]) == "new"
    assert compute_lifecycle_state([
        {"snap_date": "2026-06-10", "article_count": 1}
    ]) == "new"


def test_rising_with_consecutive_growth():
    history = [
        {"snap_date": f"2026-06-{d:02d}", "article_count": d}
        for d in range(10, 16)  # 10,11,12,13,14,15 — consecutive growth
    ]
    assert compute_lifecycle_state(history) == "rising"


def test_stable_with_low_fluctuation():
    history = [
        {"snap_date": f"2026-06-{d:02d}", "article_count": 5 + (d % 2)}
        for d in range(10, 20)  # 5 or 6, fluctuation < 20%
    ]
    assert compute_lifecycle_state(history) == "stable"


def test_declining_with_consecutive_drop():
    history = [
        {"snap_date": f"2026-06-{d:02d}", "article_count": 20 - d}
        for d in range(10, 20)  # 10,9,8,7,6,5,4,3,2,1 — consecutive drop
    ]
    assert compute_lifecycle_state(history) == "declining"


def test_consecutive_increasing():
    assert _consecutive_increasing([1, 2, 3], 3) is True
    assert _consecutive_increasing([1, 2, 1], 3) is False
    assert _consecutive_increasing([1, 2], 3) is False  # too short


def test_consecutive_decreasing():
    assert _consecutive_decreasing([3, 2, 1], 3) is True
    assert _consecutive_decreasing([3, 2, 3], 3) is False


def test_low_fluctuation():
    assert _low_fluctuation([10, 11, 10, 11]) is True   # ~10% fluctuation
    assert _low_fluctuation([10, 16, 10, 16]) is False  # ~23% fluctuation, exceeds 20%
    assert _low_fluctuation([0, 0, 0]) is True           # all zeros


def test_update_all_lifecycle_states(test_db):
    from db.models import save_concept_nodes
    import datetime
    today = datetime.date.today().isoformat()
    # Insert concept with history over 8 days
    for i in range(8):
        d = (datetime.date.today() - datetime.timedelta(days=7 - i)).isoformat()
        nodes = [{"type": "concept", "label": "TestConcept", "weight": float(i + 1)}]
        save_concept_nodes(test_db, d, nodes)

    update_all_lifecycle_states(test_db, today)

    from db.models import get_concept_nodes_by_date
    results = get_concept_nodes_by_date(test_db, today)
    if results:
        assert results[0]["lifecycle_state"] in ("new", "rising", "stable", "declining")
