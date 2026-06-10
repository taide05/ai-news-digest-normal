"""Concept lifecycle state machine with hysteresis windows."""
from collections import deque

# State transition hysteresis windows (days)
RISING_WINDOW = 3
STABLE_WINDOW = 5
DECLINING_WINDOW = 7
STABLE_FLUCTUATION = 0.20  # 20%


def compute_lifecycle_state(history: list[dict]) -> str:
    """Determine lifecycle state from a concept's daily article_count history.

    history: list of {snap_date, article_count} ordered by date ASC.
    Returns one of: new, rising, stable, declining.
    """
    if not history:
        return "new"

    counts = [h["article_count"] for h in history]

    if len(counts) < 2:
        return "new"

    recent = counts[-DECLINING_WINDOW:]
    if len(recent) < 2:
        return "new"

    # Check declining: N consecutive days decreasing
    if _consecutive_decreasing(recent, DECLINING_WINDOW):
        return "declining"

    # Check rising: N consecutive days increasing
    rising_window = counts[-RISING_WINDOW:]
    if len(rising_window) >= 2 and _consecutive_increasing(rising_window, RISING_WINDOW):
        return "rising"

    # Check stable: N days with fluctuation < 20%
    stable_window = counts[-STABLE_WINDOW:]
    if len(stable_window) >= STABLE_WINDOW and _low_fluctuation(stable_window):
        return "stable"

    # Default: keep previous state or mark as stable if long history
    if len(counts) >= 10:
        return "stable"
    return "new"


def _consecutive_increasing(values: list, window: int) -> bool:
    if len(values) < window:
        return False
    check = values[-window:]
    return all(check[i] < check[i + 1] for i in range(len(check) - 1))


def _consecutive_decreasing(values: list, window: int) -> bool:
    if len(values) < window:
        return False
    check = values[-window:]
    return all(check[i] > check[i + 1] for i in range(len(check) - 1))


def _low_fluctuation(values: list) -> bool:
    if len(values) < 2:
        return False
    avg = sum(values) / len(values)
    if avg == 0:
        return True
    max_dev = max(abs(v - avg) for v in values) / avg
    return max_dev <= STABLE_FLUCTUATION


def update_all_lifecycle_states(conn, today_str: str):
    """Update lifecycle_state for all concepts that appeared today."""
    from db.models import get_distinct_concept_labels, get_concept_node_history
    labels = get_distinct_concept_labels(conn)
    for label in labels:
        history = get_concept_node_history(conn, label, days=90)
        state = compute_lifecycle_state(history)
        conn.execute(
            "UPDATE concept_nodes SET lifecycle_state = ? "
            "WHERE concept_label = ? AND snap_date = ?",
            (state, label, today_str)
        )
    conn.commit()
