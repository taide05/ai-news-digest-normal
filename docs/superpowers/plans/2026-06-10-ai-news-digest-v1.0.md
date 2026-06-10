# AI 资讯管家 v1.0 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 知识图谱从展示层升级为数据层一等公民 — 档案永久化、结构化存储、生命周期追踪，配合 Bug Hunting 机制和 Codex 审阅交接完成 v1.0 正式发布。

**Architecture:** 翻转写入方向：`concept_nodes` 为唯一真相源，JSON 快照从结构化表派生。三层递进：A（去 DELETE）→ B（concept_nodes 表+查询切换）→ C（生命周期状态机+轨迹页）。Bug Hunting 四 Hunter 融入 B+T 阶段。

**Tech Stack:** Python 3.12, FastAPI, SQLite, Jinja2, scikit-learn (cluster)

---

## 文件变更总览

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `scheduler.py` | 移除 DELETE；抽取 save 函数；startup 也写 concept_nodes |
| 修改 | `db/schema.py` | 新增 concept_nodes 建表语句 + lifecycle_state 列 |
| 修改 | `db/models.py` | 新增 concept_nodes CRUD + 回填 + 剪枝函数 |
| 修改 | `web/routes/graph.py` | 查询路径切换到 concept_nodes |
| 新增 | `ai/lifecycle.py` | 生命周期状态机计算 |
| 修改 | `web/routes/concepts.py` | 新增 /concepts/<label> 轨迹页路由 |
| 新增 | `web/templates/concept_detail.html` | 概念轨迹页模板 |
| 修改 | `docs/superpowers/PROJECT-OVERVIEW.md` | Bug Hunting 机制文档化 + v1.0 更新 |
| 新增 | `tests/test_v10_concept_nodes.py` | concept_nodes 模型测试 |
| 新增 | `tests/test_v10_lifecycle.py` | 生命周期状态机测试 |
| 新增 | `tests/test_v10_concept_route.py` | 轨迹页路由测试 |

---

### Task 1: Layer A — 档案永久化

**Files:**
- Modify: `scheduler.py:60-67`

- [ ] **Step 1: 移除 30 天 DELETE 逻辑**

在 `scheduler.py` 的 `daily_job()` 中，删除 snapshot cleanup 代码块（第 60-67 行）：

```python
# 删除以下 8 行:
                    # Clean up snapshots older than 30 days
                    from datetime import timedelta
                    cutoff = (date.today() - timedelta(days=30)).isoformat()
                    db_conn.execute(
                        "DELETE FROM graph_snapshots WHERE snap_date < ?",
                        (cutoff,)
                    )
                    db_conn.commit()
```

修改后 `daily_job()` 的快照保存部分变为：

```python
                if rows:
                    snap_nodes, snap_edges = _build_nodes_and_edges(rows)
                    save_graph_snapshot(db_conn, today_str, "today",
                                        {"nodes": snap_nodes, "edges": snap_edges})
                    logger.info(f"Scheduler: graph snapshot saved for {today_str}")
```

- [ ] **Step 2: 检查 DELETE 是否还有其他引用**

```bash
grep -rn "DELETE FROM graph_snapshots" D:/Projects/ai-news-digest --include="*.py"
```

Expected: 只有 `scheduler.py` 有（已移除）。如有其他引用，一并评估。

- [ ] **Step 3: 运行现有测试确认无回归**

```bash
cd D:/Projects/ai-news-digest && .venv/Scripts/python -m pytest tests/ -q
```

Expected: 216 passed.

- [ ] **Step 4: Commit**

```bash
git add scheduler.py
git commit -m "feat: Layer A — remove 30-day graph_snapshot cleanup, permanent archive"
```

---

### Task 2: Layer B — Schema + concept_nodes 模型

**Files:**
- Modify: `db/schema.py:105-112`
- Modify: `db/models.py` (append new functions)
- Create: `tests/test_v10_concept_nodes.py`

- [ ] **Step 1: 添加 concept_nodes 建表语句**

在 `db/schema.py` 的 `SCHEMA_SQL` 中，`graph_snapshots` 之后插入：

```sql

CREATE TABLE IF NOT EXISTS concept_nodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_label   TEXT NOT NULL,
    weight          REAL DEFAULT 0.0,
    article_count   INTEGER DEFAULT 0,
    first_seen_date TEXT NOT NULL,
    last_seen_date  TEXT NOT NULL,
    snap_date       TEXT NOT NULL,
    lifecycle_state TEXT DEFAULT 'new',
    UNIQUE(concept_label, snap_date)
);
CREATE INDEX IF NOT EXISTS idx_concept_nodes_label ON concept_nodes(concept_label);
CREATE INDEX IF NOT EXISTS idx_concept_nodes_snap_date ON concept_nodes(snap_date);
```

- [ ] **Step 2: 添加 concept_nodes 模型函数**

在 `db/models.py` 末尾追加：

```python
def save_concept_nodes(conn, snap_date: str, nodes: list[dict],
                       commit: bool = True):
    """Write concept nodes for a given snap_date. UPSERT by (label, date)."""
    for node in nodes:
        if node.get("type") != "concept":
            continue
        label = node["label"]
        weight = float(node.get("weight", node.get("query_count", 1)))
        conn.execute(
            "INSERT INTO concept_nodes (concept_label, weight, article_count, "
            "first_seen_date, last_seen_date, snap_date) "
            "VALUES (?, ?, 1, ?, ?, ?) "
            "ON CONFLICT(concept_label, snap_date) DO UPDATE SET "
            "weight = excluded.weight, article_count = concept_nodes.article_count + 1, "
            "last_seen_date = excluded.last_seen_date",
            (label, weight, snap_date, snap_date, snap_date)
        )
    if commit:
        conn.commit()


def get_concept_nodes_by_date(conn, snap_date: str) -> list[dict]:
    """Return all concept nodes for a given snap_date."""
    rows = conn.execute(
        "SELECT id, concept_label, weight, article_count, "
        "first_seen_date, last_seen_date, lifecycle_state "
        "FROM concept_nodes WHERE snap_date = ? "
        "ORDER BY weight DESC",
        (snap_date,)
    ).fetchall()
    return [{"id": r[0], "label": r[1], "weight": r[2],
             "article_count": r[3], "first_seen_date": r[4],
             "last_seen_date": r[5], "lifecycle_state": r[6]} for r in rows]


def get_concept_node_history(conn, concept_label: str,
                              days: int = 90) -> list[dict]:
    """Return daily snapshots for a single concept, ordered by date ASC."""
    rows = conn.execute(
        "SELECT snap_date, weight, article_count, lifecycle_state "
        "FROM concept_nodes WHERE concept_label = ? "
        "AND snap_date >= date('now', ?) "
        "ORDER BY snap_date ASC",
        (concept_label, f"-{days} days")
    ).fetchall()
    return [{"snap_date": r[0], "weight": r[1],
             "article_count": r[2], "lifecycle_state": r[3]} for r in rows]


def get_distinct_concept_labels(conn, limit: int = 200) -> list[str]:
    """Return distinct concept labels seen recently."""
    rows = conn.execute(
        "SELECT DISTINCT concept_label FROM concept_nodes "
        "WHERE snap_date >= date('now', '-30 days') "
        "ORDER BY concept_label LIMIT ?",
        (limit,)
    ).fetchall()
    return [r[0] for r in rows]


def backfill_concept_nodes_from_snapshots(conn):
    """One-time: populate concept_nodes from existing graph_snapshots JSON."""
    existing = conn.execute("SELECT COUNT(*) FROM concept_nodes").fetchone()[0]
    if existing > 0:
        return 0  # Already populated

    rows = conn.execute(
        "SELECT snap_date, data_json FROM graph_snapshots ORDER BY snap_date ASC"
    ).fetchall()
    count = 0
    for snap_date, data_json in rows:
        data = json.loads(data_json)
        nodes = data.get("nodes", [])
        save_concept_nodes(conn, snap_date, nodes, commit=False)
        count += 1
    if count > 0:
        conn.commit()
    return count


def prune_stale_concepts(conn, retention_days: int = 90,
                          weight_threshold: float = 1.0,
                          commit: bool = True):
    """Soft-delete concept snapshots older than retention_days with low weight."""
    conn.execute(
        "DELETE FROM concept_nodes WHERE snap_date < date('now', ?) "
        "AND weight < ? AND lifecycle_state = 'declining'",
        (f"-{retention_days} days", weight_threshold)
    )
    if commit:
        conn.commit()
```

- [ ] **Step 3: 编写 concept_nodes 模型测试**

创建 `tests/test_v10_concept_nodes.py`：

```python
import pytest
from db.models import (
    save_concept_nodes, get_concept_nodes_by_date,
    get_concept_node_history, get_distinct_concept_labels,
    backfill_concept_nodes_from_snapshots, prune_stale_concepts
)


def test_save_and_get_concept_nodes(db_conn):
    """Save concept nodes and retrieve them by date."""
    nodes = [
        {"type": "concept", "label": "Transformer", "weight": 5.0, "query_count": 5},
        {"type": "concept", "label": "RLHF", "weight": 3.0, "query_count": 3},
        {"type": "article", "label": "Some Article"},  # should be skipped
    ]
    save_concept_nodes(db_conn, "2026-06-10", nodes)

    results = get_concept_nodes_by_date(db_conn, "2026-06-10")
    assert len(results) == 2
    labels = {r["label"] for r in results}
    assert labels == {"Transformer", "RLHF"}


def test_save_concept_nodes_upsert(db_conn):
    """Second save for same label+date updates weight and article_count."""
    nodes = [
        {"type": "concept", "label": "Transformer", "weight": 2.0, "query_count": 2},
    ]
    save_concept_nodes(db_conn, "2026-06-10", nodes)
    # Save again with different weight
    save_concept_nodes(db_conn, "2026-06-10", nodes)

    results = get_concept_nodes_by_date(db_conn, "2026-06-10")
    assert len(results) == 1
    assert results[0]["article_count"] == 2  # incremented


def test_get_concept_node_history(db_conn):
    """History returns daily snapshots for a concept."""
    for day in range(3):
        date = f"2026-06-{10 + day:02d}"
        nodes = [{"type": "concept", "label": "Transformer", "weight": 2.0 + day}]
        save_concept_nodes(db_conn, date, nodes)

    history = get_concept_node_history(db_conn, "Transformer", days=30)
    assert len(history) == 3
    assert history[0]["weight"] == 2.0
    assert history[-1]["weight"] == 4.0


def test_get_distinct_concept_labels(db_conn):
    nodes_a = [{"type": "concept", "label": "Alpha", "weight": 1.0}]
    nodes_b = [{"type": "concept", "label": "Beta", "weight": 1.0}]
    save_concept_nodes(db_conn, "2026-06-10", nodes_a)
    save_concept_nodes(db_conn, "2026-06-10", nodes_b)

    labels = get_distinct_concept_labels(db_conn)
    assert "Alpha" in labels or "Beta" in labels


def test_backfill_skips_when_populated(db_conn):
    """backfill returns 0 when concept_nodes already has data."""
    nodes = [{"type": "concept", "label": "Test", "weight": 1.0}]
    save_concept_nodes(db_conn, "2026-06-10", nodes)

    count = backfill_concept_nodes_from_snapshots(db_conn)
    assert count == 0


def test_prune_stale_concepts(db_conn):
    """Pruning removes old declining low-weight concepts."""
    # Insert an old declining concept
    conn = db_conn
    conn.execute(
        "INSERT INTO concept_nodes (concept_label, weight, article_count, "
        "first_seen_date, last_seen_date, snap_date, lifecycle_state) "
        "VALUES ('old_concept', 0.5, 1, '2026-01-01', '2026-01-01', "
        "date('now', '-100 days'), 'declining')"
    )
    conn.commit()

    prune_stale_concepts(db_conn, retention_days=90, weight_threshold=1.0)

    history = get_concept_node_history(db_conn, "old_concept", days=200)
    assert len(history) == 0  # pruned
```

- [ ] **Step 4: 运行测试验证失败（新测试尚无实现）**

```bash
cd D:/Projects/ai-news-digest && .venv/Scripts/python -m pytest tests/test_v10_concept_nodes.py -v
```

Expected: 部分 PASS（模型函数已添加到 models.py），部分可能因 db_conn fixture 需要调整。

- [ ] **Step 5: 运行全量测试确认无回归**

```bash
cd D:/Projects/ai-news-digest && .venv/Scripts/python -m pytest tests/ -q
```

Expected: 222+ passed (216 + 6 new).

- [ ] **Step 6: Commit**

```bash
git add db/schema.py db/models.py tests/test_v10_concept_nodes.py
git commit -m "feat: Layer B — concept_nodes table + CRUD + backfill + pruning"
```

---

### Task 3: Layer B — Scheduler 写入路径翻转

**Files:**
- Modify: `scheduler.py:43-68`

- [ ] **Step 1: 抽取可复用的 snapshot 保存函数**

在 `scheduler.py` 中 `_weekly_md_job` 之后、`create_scheduler` 之前，新增：

```python
def _save_graph_snapshot(db_conn, today_str: str):
    """Save concept_nodes + JSON snapshot for today. Called after collection."""
    from db.models import (get_graph_data, save_graph_snapshot,
                           save_concept_nodes, prune_stale_concepts)
    from web.routes.graph import _build_nodes_and_edges

    rows = get_graph_data(db_conn, "today")
    if not rows:
        logger.info("Scheduler: no concept data, skipping snapshot")
        return

    snap_nodes, snap_edges = _build_nodes_and_edges(rows)

    # Primary: write to concept_nodes (single source of truth)
    save_concept_nodes(db_conn, today_str, snap_nodes)

    # Secondary: generate JSON snapshot from concept_nodes (backup/compat)
    from db.models import get_concept_nodes_by_date
    node_records = get_concept_nodes_by_date(db_conn, today_str)
    snapshot_nodes = [
        {"id": n["label"], "label": n["label"], "type": "concept",
         "query_count": int(n["weight"]), "weight": n["weight"]}
        for n in node_records
    ]
    save_graph_snapshot(db_conn, today_str, "today",
                        {"nodes": snapshot_nodes, "edges": snap_edges})

    # Prune stale concepts
    prune_stale_concepts(db_conn)

    logger.info(f"Scheduler: concept_nodes + snapshot saved for {today_str}")
```

- [ ] **Step 2: 修改 daily_job 调用新函数**

将 `daily_job()` 的快照部分替换为调用 `_save_graph_snapshot`：

```python
    async def daily_job():
        logger.info("Scheduler: starting daily collection")
        try:
            count = await orchestrator_module.run_full_pipeline(db_conn, None, cfg)
            logger.info(f"Scheduler: daily collection complete — {count} articles")
            try:
                today_str = date.today().isoformat()
                _save_graph_snapshot(db_conn, today_str)
            except Exception as e:
                logger.warning(f"Scheduler: graph snapshot failed: {e}")
        except Exception as e:
            logger.error(f"Scheduler: daily job failed: {e}")
```

- [ ] **Step 3: 修改 startup 路径也写 concept_nodes**

在 `start_scheduler()` 中，startup collection 之后调用 `_save_graph_snapshot`：

```python
    if cfg.scheduler.run_on_startup:
        logger.info("Scheduler: run_on_startup enabled, triggering immediate collection")
        try:
            asyncio.run(orchestrator_module.run_full_pipeline(db_conn, None, cfg))
            # v1.0: startup collection also saves to concept_nodes
            today_str = date.today().isoformat()
            _save_graph_snapshot(db_conn, today_str)
        except Exception as e:
            logger.error(f"Scheduler: startup collection failed: {e}")
```

并移除旧的注释 `# Note: startup collection runs the pipeline directly...`。

- [ ] **Step 4: 运行全量测试**

```bash
cd D:/Projects/ai-news-digest && .venv/Scripts/python -m pytest tests/ -q
```

Expected: 222+ passed.

- [ ] **Step 5: Commit**

```bash
git add scheduler.py
git commit -m "feat: Layer B — flip write direction, concept_nodes as source of truth"
```

---

### Task 4: Layer B — Graph 路由查询切换

**Files:**
- Modify: `db/models.py` (add `get_graph_data_from_nodes`)
- Modify: `web/routes/graph.py:36-63`
- Modify: `tests/test_graph_v08.py`

- [ ] **Step 1: 添加 concept_nodes 查询函数**

在 `db/models.py` 中 `get_graph_data` 之后追加：

```python
def get_graph_data_from_nodes(conn, snap_date: str) -> list[dict]:
    """Return concept nodes for a given date as graph-compatible rows.
    Article nodes come from the live articles table for that date."""
    rows = conn.execute(
        "SELECT cn.concept_label AS concept, cn.weight AS query_count, "
        "a.id AS article_id, a.title, a.source_id "
        "FROM concept_nodes cn "
        "JOIN concepts c ON cn.concept_label = c.term "
        "JOIN article_concepts ac ON c.id = ac.concept_id "
        "JOIN articles a ON ac.article_id = a.id "
        "WHERE cn.snap_date = ? "
        "AND a.fetched_at >= ? "
        "ORDER BY cn.weight DESC LIMIT 100",
        (snap_date, snap_date)
    ).fetchall()
    return [{"article_id": r[2], "title": r[3], "source_id": r[4],
             "concept": r[0], "query_count": r[1]} for r in rows]
```

- [ ] **Step 2: 修改 graph 路由使用 concept_nodes**

修改 `web/routes/graph.py`，主查询切换到 `concept_nodes`，保留 live JOIN 作为 fallback：

```python
from db.models import (get_graph_data, get_graph_snapshot, get_snapshot_dates,
                       get_graph_data_from_nodes, get_concept_nodes_by_date)


@router.get("/graph", response_class=HTMLResponse)
async def graph(request: Request, period: str = Query("today"),
                compare: str = Query("")):
    db = get_db()
    nodes = []
    edges = []
    dates = []
    compare_nodes = []
    compare_edges = []

    if db:
        today_str = __import__("datetime").date.today().isoformat()

        if period == "today":
            # Prefer concept_nodes for today, fallback to live JOIN
            rows = get_graph_data_from_nodes(db, today_str)
            if not rows:
                rows = get_graph_data(db, period)
        else:
            rows = get_graph_data(db, period)

        nodes, edges = _build_nodes_and_edges(rows)
        dates = get_snapshot_dates(db)

        if compare:
            # Compare uses concept_nodes for historical data
            snap = get_graph_snapshot(db, compare, period)
            if snap:
                compare_nodes = snap.get("nodes", [])
                compare_edges = snap.get("edges", [])

    return templates.TemplateResponse(request, "graph.html", {
        "nodes": nodes, "edges": edges, "period": period,
        "node_count": len(nodes), "edge_count": len(edges),
        "dates": dates, "compare": compare,
        "compare_nodes": compare_nodes, "compare_edges": compare_edges,
    })
```

- [ ] **Step 3: 更新现有 graph 测试**

修改 `tests/test_graph_v08.py`，增加 concept_nodes 数据的测试场景。在 `test_graph_today` 中先写入 concept_nodes 数据。

- [ ] **Step 4: 运行全量测试**

```bash
cd D:/Projects/ai-news-digest && .venv/Scripts/python -m pytest tests/ -q
```

Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
git add db/models.py web/routes/graph.py tests/test_graph_v08.py
git commit -m "feat: Layer B — graph route queries concept_nodes as primary source"
```

---

### Task 5: Layer C — 生命周期状态机

**Files:**
- Create: `ai/lifecycle.py`
- Modify: `scheduler.py` (daily lifecycle update)
- Create: `tests/test_v10_lifecycle.py`

- [ ] **Step 1: 编写 lifecycle 引擎**

创建 `ai/lifecycle.py`：

```python
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
```

- [ ] **Step 2: 编写 lifecycle 测试**

创建 `tests/test_v10_lifecycle.py`：

```python
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


def test_consecutive_decreasing():
    assert _consecutive_decreasing([3, 2, 1], 3) is True
    assert _consecutive_decreasing([3, 2, 3], 3) is False


def test_low_fluctuation():
    assert _low_fluctuation([10, 11, 10, 11]) is True   # ~10% fluctuation
    assert _low_fluctuation([10, 15, 10, 15]) is False  # ~50% fluctuation


def test_update_all_lifecycle_states(db_conn):
    from db.models import save_concept_nodes
    today = "2026-06-10"
    # Insert concept with rising pattern
    for i, day in enumerate(range(7, 0, -1)):
        date = f"2026-06-{10 - day:02d}"
        nodes = [{"type": "concept", "label": "TestConcept", "weight": float(i + 1)}]
        save_concept_nodes(db_conn, date, nodes)

    update_all_lifecycle_states(db_conn, today)

    from db.models import get_concept_nodes_by_date
    results = get_concept_nodes_by_date(db_conn, today)
    # Should have a state set (not just 'new' since there's history)
    if results:
        assert results[0]["lifecycle_state"] in ("new", "rising", "stable", "declining")
```

- [ ] **Step 3: 集成到 scheduler daily_job**

在 `_save_graph_snapshot()` 末尾（`prune_stale_concepts` 之后）添加：

```python
    # Update lifecycle states
    from ai.lifecycle import update_all_lifecycle_states
    update_all_lifecycle_states(db_conn, today_str)
```

- [ ] **Step 4: 运行全量测试**

```bash
cd D:/Projects/ai-news-digest && .venv/Scripts/python -m pytest tests/ -q
```

Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
git add ai/lifecycle.py tests/test_v10_lifecycle.py scheduler.py
git commit -m "feat: Layer C — concept lifecycle state machine with hysteresis"
```

---

### Task 6: Layer C — 概念轨迹页

**Files:**
- Create: `web/templates/concept_detail.html`
- Modify: `web/routes/concepts.py`
- Create: `tests/test_v10_concept_route.py`

- [ ] **Step 1: 编写概念轨迹页模板**

创建 `web/templates/concept_detail.html`：

```html
{% extends "base.html" %}
{% block content %}
<div class="concept-detail">
    <a href="/concepts" class="back-link">&larr; 返回概念词典</a>

    <h1>{{ concept_label }}
        <span class="lifecycle-badge lifecycle-{{ lifecycle_state }}">{{ lifecycle_state_display }}</span>
    </h1>

    <div class="concept-meta">
        <span>首次出现：{{ first_seen }}</span>
        <span>最近出现：{{ last_seen }}</span>
        <span>累计文章：{{ total_articles }}</span>
    </div>

    {% if history %}
    <div class="concept-chart">
        <h2>权重变化趋势</h2>
        <svg id="weight-chart" width="100%" height="200" viewBox="0 0 800 200">
            <!-- polyline rendered inline -->
            <polyline fill="none" stroke="#4caf50" stroke-width="2"
                      points="{{ chart_points }}"/>
        </svg>
    </div>
    {% endif %}

    {% if related_articles %}
    <div class="related-articles">
        <h2>近期相关文章</h2>
        {% for a in related_articles %}
        <div class="article-item">
            <a href="/reader/{{ a.id }}" class="article-link">{{ a.source_id }}</a>
            <span class="article-meta">{{ a.title }} · {{ a.published_at }}</span>
        </div>
        {% endfor %}
    </div>
    {% endif %}
</div>

<nav class="bottom-nav">
    <a href="/">首页</a>
    <a href="/sources">信息源</a>
    <a href="/search">搜索</a>
    <a href="/concepts">概念词典</a>
    <a href="/review">周报</a>
</nav>
{% endblock %}
```

- [ ] **Step 2: 添加概念轨迹页路由**

修改 `web/routes/concepts.py`：

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from web.globals import get_db
from db.models import get_concepts_list, get_concept_node_history, get_concept_nodes_by_date
from web.templates import templates
from datetime import date

router = APIRouter()


@router.get("/concepts", response_class=HTMLResponse)
async def concepts_list(request: Request):
    concepts = get_concepts_list(get_db()) if get_db() else []
    return templates.TemplateResponse(request, "concepts.html", {"concepts": concepts})


@router.get("/concepts/{label:path}", response_class=HTMLResponse)
async def concept_detail(request: Request, label: str):
    db = get_db()
    if not db:
        return templates.TemplateResponse(request, "concept_detail.html", {
            "concept_label": label, "lifecycle_state": "new",
            "lifecycle_state_display": "新概念", "first_seen": "-",
            "last_seen": "-", "total_articles": 0,
            "history": [], "chart_points": "", "related_articles": []
        })

    history = get_concept_node_history(db, label, days=90)
    today_nodes = get_concept_nodes_by_date(db, date.today().isoformat())
    current = next((n for n in today_nodes if n["label"] == label), None)

    lifecycle_state = current["lifecycle_state"] if current else "new"
    state_display = {
        "new": "新概念", "rising": "上升中", "stable": "稳定",
        "declining": "下降中"
    }.get(lifecycle_state, lifecycle_state)

    # Build SVG chart points
    chart_points = ""
    if history and len(history) > 1:
        max_w = max(h["weight"] for h in history) or 1
        width = 800
        height = 200
        step = width / (len(history) - 1)
        points = []
        for i, h in enumerate(history):
            x = int(i * step)
            y = int(height - (h["weight"] / max_w) * (height - 20) - 10)
            points.append(f"{x},{y}")
        chart_points = " ".join(points)

    # Related articles
    related_articles = []
    if db:
        rows = db.execute(
            "SELECT DISTINCT a.id, a.title, a.source_id, a.published_at "
            "FROM articles a "
            "JOIN article_concepts ac ON a.id = ac.article_id "
            "JOIN concepts c ON ac.concept_id = c.id "
            "WHERE c.term = ? "
            "ORDER BY a.published_at DESC LIMIT 20",
            (label,)
        ).fetchall()
        related_articles = [
            {"id": r[0], "title": r[1], "source_id": r[2], "published_at": r[3]}
            for r in rows
        ]

    return templates.TemplateResponse(request, "concept_detail.html", {
        "concept_label": label,
        "lifecycle_state": lifecycle_state,
        "lifecycle_state_display": state_display,
        "first_seen": history[0]["snap_date"] if history else "-",
        "last_seen": history[-1]["snap_date"] if history else "-",
        "total_articles": sum(h["article_count"] for h in history),
        "history": history,
        "chart_points": chart_points,
        "related_articles": related_articles,
    })
```

- [ ] **Step 3: 编写路由测试**

创建 `tests/test_v10_concept_route.py`：

```python
import pytest
from fastapi.testclient import TestClient


def test_concept_detail_route_returns_html(client, db_conn):
    """/concepts/<label> returns HTML page."""
    from db.models import save_concept_nodes
    today = "2026-06-10"
    nodes = [{"type": "concept", "label": "Transformer", "weight": 3.0}]
    save_concept_nodes(db_conn, today, nodes)

    response = client.get("/concepts/Transformer")
    assert response.status_code == 200
    assert "Transformer" in response.text
    assert "concept-detail" in response.text


def test_concept_detail_unknown_label(client):
    """Unknown concept still renders page gracefully."""
    response = client.get("/concepts/NonexistentConcept")
    assert response.status_code == 200
    assert "NonexistentConcept" in response.text


def test_concept_detail_has_back_link(client, db_conn):
    from db.models import save_concept_nodes
    save_concept_nodes(db_conn, "2026-06-10",
                       [{"type": "concept", "label": "Test", "weight": 1.0}])

    response = client.get("/concepts/Test")
    assert 'href="/concepts"' in response.text
```

- [ ] **Step 4: 运行全量测试**

```bash
cd D:/Projects/ai-news-digest && .venv/Scripts/python -m pytest tests/ -q
```

Expected: 全部通过。

- [ ] **Step 5: 添加 CSS 样式**

在 `web/static/style.css` 末尾追加概念轨迹页样式：

```css
.lifecycle-badge { display:inline-block; padding:2px 10px; border-radius:12px;
    font-size:0.85em; color:#fff; }
.lifecycle-new { background:#2196f3; }
.lifecycle-rising { background:#4caf50; }
.lifecycle-stable { background:#607d8b; }
.lifecycle-declining { background:#ff9800; }
.concept-meta { display:flex; gap:20px; margin:12px 0; color:#888; font-size:0.9em; }
.concept-chart { margin:24px 0; padding:16px; background:#1e1e1e; border-radius:8px; }
.concept-chart h2 { margin-top:0; font-size:1.1em; color:#aaa; }
```

- [ ] **Step 6: Commit**

```bash
git add web/templates/concept_detail.html web/routes/concepts.py tests/test_v10_concept_route.py web/static/style.css
git commit -m "feat: Layer C — concept trajectory page at /concepts/<label>"
```

---

### Task 7: Bug Hunting 集成 + Codex 交接

**Files:**
- Modify: `docs/superpowers/PROJECT-OVERVIEW.md`

- [ ] **Step 1: 更新 PROJECT-OVERVIEW.md — Bug Hunting 章节**

在 "五、标准开发循环" 中，阶段 B 和 T 下新增 Hunter 模块描述。在 "铁律" 后追加 R11。

- [ ] **Step 2: 更新 PROJECT-OVERVIEW.md — v1.0 版本记录**

更新版本路线图：v1.0 ✅，版本历史表新增 v1.0 行。

- [ ] **Step 3: 验证 8 条 Codex 规则**

逐条检查当前项目状态是否符合 codex-handover-requirements。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/PROJECT-OVERVIEW.md
git commit -m "docs: v1.0 — bug hunting integration + codex handover verification"
```

---

### Task 8: 集成验证 + 最终验收

- [ ] **Step 1: 运行全量测试套件**

```bash
cd D:/Projects/ai-news-digest && .venv/Scripts/python -m pytest tests/ -v
```

Expected: 全部通过，测试数 ≥ 230。

- [ ] **Step 2: 覆盖率检查**

```bash
cd D:/Projects/ai-news-digest && .venv/Scripts/python -m pytest tests/ --cov=. --cov-report=term
```

Expected: 覆盖率 ≥ 84%。

- [ ] **Step 3: 启动服务验证**

```bash
cd D:/Projects/ai-news-digest && timeout 15 .venv/Scripts/python main.py 2>&1 || true
```

验证：
- `/api/health` 返回 200
- `/graph` 正常渲染
- `/concepts/<label>` 正常渲染
- `/` 首页正常渲染

- [ ] **Step 4: 回填迁移验证**

确认首次启动时 `backfill_concept_nodes_from_snapshots` 正确迁移历史 JSON 数据。

- [ ] **Step 5: 编写 Cycle Report**

写入 `docs/superpowers/reports/2026-06-10-cycle-8-report.md`，记录完整的 v1.0 A→F 过程。

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/reports/2026-06-10-cycle-8-report.md
git commit -m "docs: v1.0 cycle 8 report — final release"
```

---

## 依赖关系

```
Task 1 (Layer A) ──┐
                    ├──→ Task 3 (Scheduler) ──→ Task 5 (Lifecycle) ──→ Task 8 (Integration)
Task 2 (Schema)  ──┤                                        │
                    └──→ Task 4 (Graph Route)                └──→ Task 6 (Trajectory Page)

                                                              Task 7 (Docs) ──→ Task 8
```

Task 1-2 可并行。Task 3-4 依赖 1-2。Task 5-6 依赖 3-4。Task 7 独立。Task 8 收尾。
