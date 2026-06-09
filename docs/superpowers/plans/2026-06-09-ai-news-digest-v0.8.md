# AI 资讯管家 v0.8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打磨收尾——图谱历史对比 + 推荐聚类升级 + 周报数据驱动，为 v1.0 做最后润色

**Architecture:** 3 个独立模块在现有文件上增量修改。graph_snapshots 表支持历史快照，推荐引擎 B 从 gap 升级为 cluster，周报注入统计数据。不新增路由/页面。

**Tech Stack:** Python 3.13, FastAPI, SQLite WAL, Jinja2 + htmx, APScheduler

---

### Task 1: 知识图谱历史对比

**Files:**
- Modify: `D:\Projects\ai-news-digest\db\schema.py` — 新增 `graph_snapshots` 表
- Modify: `D:\Projects\ai-news-digest\db\models.py` — 新增 `save_graph_snapshot`, `get_graph_snapshot`, `get_snapshot_dates`
- Modify: `D:\Projects\ai-news-digest\web\routes\graph.py` — 支持 `?compare=` + 历史日期列表
- Modify: `D:\Projects\ai-news-digest\web\templates\graph.html` — tab 切换 + 对比模式双 SVG
- Modify: `D:\Projects\ai-news-digest\scheduler.py` — daily_job 完成后生成 snapshot
- Create: `D:\Projects\ai-news-digest\tests\test_graph_v08.py`

- [ ] **Step 1: Add graph_snapshots table to db/schema.py**

In `D:\Projects\ai-news-digest\db\schema.py`, add after the `cross_analysis_cache` table definition (after line 103):

```sql
CREATE TABLE IF NOT EXISTS graph_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    snap_date   TEXT NOT NULL,
    period      TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(snap_date, period)
);
```

- [ ] **Step 2: Add snapshot CRUD functions to db/models.py**

Append to `D:\Projects\ai-news-digest\db\models.py`:

```python
def save_graph_snapshot(conn, snap_date: str, period: str, data: dict,
                        commit: bool = True):
    """Save a graph snapshot for a given date and period."""
    data_json = json.dumps(data)
    try:
        conn.execute(
            "INSERT INTO graph_snapshots (snap_date, period, data_json) VALUES (?, ?, ?)",
            (snap_date, period, data_json)
        )
        if commit:
            conn.commit()
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE graph_snapshots SET data_json = ? WHERE snap_date = ? AND period = ?",
            (data_json, snap_date, period)
        )
        if commit:
            conn.commit()


def get_graph_snapshot(conn, snap_date: str, period: str) -> dict | None:
    """Return a saved graph snapshot, or None."""
    row = conn.execute(
        "SELECT data_json FROM graph_snapshots WHERE snap_date = ? AND period = ?",
        (snap_date, period)
    ).fetchone()
    return json.loads(row[0]) if row else None


def get_snapshot_dates(conn, limit: int = 7) -> list[str]:
    """Return recent snapshot dates, newest first."""
    rows = conn.execute(
        "SELECT DISTINCT snap_date FROM graph_snapshots "
        "ORDER BY snap_date DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [r[0] for r in rows]
```

- [ ] **Step 3: Write tests for snapshot CRUD**

Create `D:\Projects\ai-news-digest\tests\test_graph_v08.py`:

```python
import json


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
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_graph_v08.py -v`
Expected: 4 PASS

- [ ] **Step 4: Update graph.py route — extract helper, support history + compare**

In `D:\Projects\ai-news-digest\web\routes\graph.py`, extract a `_build_nodes_and_edges` helper, then update the `graph` function:

```python
from db.models import get_graph_data, get_graph_snapshot, get_snapshot_dates


def _build_nodes_and_edges(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Convert raw DB rows into deduplicated node/edge lists."""
    nodes = []
    edges = []
    seen_articles = set()
    seen_concepts = set()
    for r in rows:
        aid = r["article_id"]
        concept = r["concept"]
        if aid not in seen_articles:
            nodes.append({
                "id": aid, "label": r["title"][:20],
                "type": "article", "source_id": r["source_id"]
            })
            seen_articles.add(aid)
        if concept not in seen_concepts:
            nodes.append({
                "id": concept, "label": concept,
                "type": "concept", "query_count": r["query_count"]
            })
            seen_concepts.add(concept)
        edges.append({"from": aid, "to": concept})
    return nodes, edges


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
        rows = get_graph_data(db, period)
        nodes, edges = _build_nodes_and_edges(rows)

        dates = get_snapshot_dates(db)

        if compare:
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

- [ ] **Step 5: Update graph.html with tab switching + compare mode**

Replace the content of `D:\Projects\ai-news-digest\web\templates\graph.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1>资讯关联图</h1>

<div style="margin-bottom:12px;">
    <a href="/graph?period=today" class="btn" style="{% if period=='today' and not compare %}font-weight:bold;{% endif %}">今天</a>
    {% if dates|length > 0 %}
    <a href="/graph?period=week" class="btn" style="{% if period=='week' and not compare %}font-weight:bold;{% endif %}">本周</a>
    {% endif %}
    {% if dates|length > 1 %}
    <select id="compare-select" onchange="if(this.value)location.href='/graph?period={{period}}&compare='+this.value" style="margin-left:8px;padding:4px 8px;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:4px;">
        <option value="">对比历史...</option>
        {% for d in dates %}
        <option value="{{ d }}" {% if compare==d %}selected{% endif %}>{{ d }}</option>
        {% endfor %}
    </select>
    {% if compare %}
    <a href="/graph?period={{ period }}" class="btn" style="margin-left:4px;">✕ 取消对比</a>
    {% endif %}
    {% endif %}
</div>

{% if nodes|length == 0 %}
<div class="empty-state"><p>{{ '今天' if period=='today' else '本周' }}还没有已分析的文章。</p></div>
{% else %}
{% if compare and compare_nodes|length > 0 %}
<div style="display:flex;gap:16px;flex-wrap:wrap;">
    <div style="flex:1;min-width:300px;">
        <div style="text-align:center;color:#888;margin-bottom:4px;">{{ period }} · 当前</div>
        <svg id="graph-svg" width="100%" height="400" style="background:var(--surface);border-radius:8px;"></svg>
    </div>
    <div style="flex:1;min-width:300px;">
        <div style="text-align:center;color:#888;margin-bottom:4px;">{{ compare }}</div>
        <svg id="compare-svg" width="100%" height="400" style="background:var(--surface);border-radius:8px;"></svg>
    </div>
</div>
{% else %}
<div style="text-align:center;color:#888;margin-bottom:8px;">{{ node_count }} 个节点 · {{ edge_count }} 条边</div>
<svg id="graph-svg" width="100%" height="500" style="background:var(--surface);border-radius:8px;"></svg>
{% endif %}
{% endif %}

<nav class="bottom-nav">
    <a href="/">首页</a>
    <a href="/sources">信息源</a>
    <a href="/search">搜索</a>
    <a href="/concepts">概念词典</a>
    <a href="/review">周报</a>
</nav>

<script>
function drawGraph(svgId, nodesData, edgesData) {
    var svg = document.getElementById(svgId);
    if (!svg) return;
    var width = svg.clientWidth || 800;
    var height = parseInt(svg.getAttribute('height'));

    var positions = {};
    var R = 8;
    nodesData.forEach(function(n) {
        positions[n.id] = {
            x: Math.random() * (width - 100) + 50,
            y: Math.random() * (height - 100) + 50,
            vx: 0, vy: 0
        };
    });

    for (var iter = 0; iter < 50; iter++) {
        var ids = Object.keys(positions);
        for (var i = 0; i < ids.length; i++) {
            for (var j = i + 1; j < ids.length; j++) {
                var a = positions[ids[i]], b = positions[ids[j]];
                var dx = a.x - b.x, dy = a.y - b.y;
                var dist = Math.sqrt(dx * dx + dy * dy) || 1;
                var force = 500 / (dist * dist);
                a.vx += (dx / dist) * force; a.vy += (dy / dist) * force;
                b.vx -= (dx / dist) * force; b.vy -= (dy / dist) * force;
            }
        }
        edgesData.forEach(function(e) {
            var a = positions[e.from], b = positions[e.to];
            if (!a || !b) return;
            var dx = b.x - a.x, dy = b.y - a.y;
            var dist = Math.sqrt(dx * dx + dy * dy) || 1;
            var force = dist * 0.01;
            a.vx += (dx / dist) * force; a.vy += (dy / dist) * force;
            b.vx -= (dx / dist) * force; b.vy -= (dy / dist) * force;
        });
        ids.forEach(function(id) {
            var p = positions[id];
            p.x += p.vx * 0.5; p.y += p.vy * 0.5;
            p.x = Math.max(R, Math.min(width - R, p.x));
            p.y = Math.max(R, Math.min(height - R, p.y));
            p.vx *= 0.9; p.vy *= 0.9;
        });
    }

    edgesData.forEach(function(e) {
        var a = positions[e.from], b = positions[e.to];
        if (!a || !b) return;
        var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
        line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
        line.setAttribute('stroke', '#555'); line.setAttribute('stroke-width', '0.5');
        line.setAttribute('opacity', '0.4');
        svg.appendChild(line);
    });
    nodesData.forEach(function(n) {
        var p = positions[n.id];
        var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', p.x); circle.setAttribute('cy', p.y);
        var r = n.type === 'concept' ? Math.min(4 + (n.query_count || 1), 16) : 6;
        circle.setAttribute('r', r);
        circle.setAttribute('fill', n.type === 'concept' ? '#2196f3' : '#ff9800');
        circle.setAttribute('style', 'cursor:pointer;');
        circle.setAttribute('onclick', n.type === 'concept'
            ? "location.href='/search?q=" + encodeURIComponent(n.label) + "'"
            : "location.href='/reader/" + n.id + "'");
        var title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = n.label;
        circle.appendChild(title);
        svg.appendChild(circle);
        var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', p.x + r + 2); text.setAttribute('y', p.y + 4);
        text.setAttribute('fill', '#ccc'); text.setAttribute('font-size', '10');
        text.textContent = n.label.substring(0, 15);
        svg.appendChild(text);
    });
}

{% if nodes|length > 0 %}
drawGraph('graph-svg', {{ nodes | tojson }}, {{ edges | tojson }});
{% endif %}
{% if compare and compare_nodes|length > 0 %}
drawGraph('compare-svg', {{ compare_nodes | tojson }}, {{ compare_edges | tojson }});
{% endif %}
</script>
{% endblock %}
```

- [ ] **Step 6: Add snapshot generation + cleanup to scheduler.py daily_job**

In `D:\Projects\ai-news-digest\scheduler.py`, inside the `daily_job` async function, after `logger.info(f"Scheduler: daily collection complete — {count} articles")`, add snapshot generation AFTER collection is confirmed complete. Also add a 30-day cleanup of old snapshots:

```python
                # Generate graph snapshot AFTER collection completes
                try:
                    from db.models import get_graph_data, save_graph_snapshot
                    from datetime import date
                    today_str = date.today().isoformat()
                    rows = get_graph_data(db_conn, "today")
                    if rows:  # Only snapshot if there's data
                        seen_a = set()
                        seen_c = set()
                        snap_nodes = []
                        snap_edges = []
                        for r in rows:
                            if r["article_id"] not in seen_a:
                                snap_nodes.append({"id": r["article_id"], "label": r["title"][:20],
                                                   "type": "article", "source_id": r["source_id"]})
                                seen_a.add(r["article_id"])
                            if r["concept"] not in seen_c:
                                snap_nodes.append({"id": r["concept"], "label": r["concept"],
                                                   "type": "concept", "query_count": r["query_count"]})
                                seen_c.add(r["concept"])
                            snap_edges.append({"from": r["article_id"], "to": r["concept"]})
                        save_graph_snapshot(db_conn, today_str, "today",
                                            {"nodes": snap_nodes, "edges": snap_edges})
                        logger.info(f"Scheduler: graph snapshot saved for {today_str}")

                        # Clean up snapshots older than 30 days
                        cutoff = date.today().replace(day=1)  # simplified: keep current month
                        db_conn.execute(
                            "DELETE FROM graph_snapshots WHERE snap_date < ?",
                            (date.today().replace(day=date.today().day - 30).isoformat(),)
                        )
                        db_conn.commit()
                except Exception as e:
                    logger.warning(f"Scheduler: graph snapshot failed: {e}")
```

Note: snapshot generation is guarded by `if rows:` — if today has no concept-annotated articles (v0.7 just launched), no empty snapshot is saved.

Also add `from datetime import date` to the imports at the top of scheduler.py if not already present.

- [ ] **Step 7: Write page tests for graph history**

Add to `tests/test_graph_v08.py`:

```python
import pytest
import os, tempfile
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals
from web.routes import graph
from db.schema import init_db


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
    # No snapshots in fresh DB, so no compare select dropdown
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
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_graph_v08.py -v`
Expected: 7 PASS

- [ ] **Step 8: Commit**

```bash
git add db/schema.py db/models.py web/routes/graph.py web/templates/graph.html scheduler.py tests/test_graph_v08.py
git commit -m "feat: graph history comparison — snapshots table, today/week/compare tabs, dual SVG"
```

---

### Task 2: 阅读推荐聚类升级

**Files:**
- Modify: `D:\Projects\ai-news-digest\db\models.py` — 新增 `get_recommendations_cluster`
- Modify: `D:\Projects\ai-news-digest\web\routes\api.py` — 推荐端点切换到 cluster，加降级逻辑
- Create: `D:\Projects\ai-news-digest\tests\test_recommend_v08.py`

- [ ] **Step 1: Add get_recommendations_cluster to db/models.py**

Append to `D:\Projects\ai-news-digest\db\models.py`:

```python
def get_recommendations_cluster(conn, limit: int = 2) -> list[dict]:
    """Recommend articles based on recent reading topic clusters.
    Falls back to empty list if user has no recent reads.
    """
    rows = conn.execute(
        "SELECT a.id, a.title, a.source_id, c.term, COUNT(*) as matches "
        "FROM articles a "
        "JOIN article_concepts ac ON a.id = ac.article_id "
        "JOIN concepts c ON ac.concept_id = c.id "
        "WHERE ac.concept_id IN ("
        "  SELECT ac2.concept_id FROM article_concepts ac2 "
        "  JOIN read_records rr ON ac2.article_id = rr.article_id "
        "  WHERE rr.opened_at >= date('now', '-7 days')"
        "  GROUP BY ac2.concept_id ORDER BY COUNT(*) DESC LIMIT 10"
        ") "
        "AND a.id NOT IN (SELECT article_id FROM read_records) "
        "GROUP BY a.id "
        "ORDER BY matches DESC, a.fetched_at DESC "
        "LIMIT ?",
        (limit,)
    ).fetchall()
    return [{"id": r[0], "title": r[1], "source_id": r[2],
             "reason": f"近期关注「{r[3]}」"} for r in rows]
```

- [ ] **Step 2: Write test for cluster recommendations**

Create `D:\Projects\ai-news-digest\tests\test_recommend_v08.py`:

```python
def test_recommendations_cluster_empty(test_db):
    from db.models import get_recommendations_cluster
    result = get_recommendations_cluster(test_db, 2)
    assert result == []


def test_recommendations_cluster_finds_recent_topics(test_db):
    from db.models import (get_recommendations_cluster, insert_article,
                           get_or_create_concept, link_article_concept, record_read)
    from db.url_utils import make_article_id

    insert_article(test_db, "hackernews", "https://example.com/c1", "Cluster Article 1", commit=False)
    insert_article(test_db, "hackernews", "https://example.com/c2", "Cluster Target", commit=False)
    aid1 = make_article_id("hackernews", "https://example.com/c1")
    aid2 = make_article_id("hackernews", "https://example.com/c2")

    cid = get_or_create_concept(test_db, "transformer", commit=False)
    link_article_concept(test_db, aid1, cid, commit=False)
    link_article_concept(test_db, aid2, cid, commit=False)
    record_read(test_db, aid1, commit=True)

    result = get_recommendations_cluster(test_db, 2)
    assert len(result) == 1
    assert result[0]["id"] == aid2
    assert "近期关注" in result[0]["reason"]
    assert "transformer" in result[0]["reason"]


def test_recommendations_cluster_excludes_read(test_db):
    from db.models import (get_recommendations_cluster, insert_article,
                           get_or_create_concept, link_article_concept, record_read)
    from db.url_utils import make_article_id

    insert_article(test_db, "hackernews", "https://example.com/c3", "Read Article", commit=False)
    insert_article(test_db, "hackernews", "https://example.com/c4", "Also Read", commit=False)
    aid1 = make_article_id("hackernews", "https://example.com/c3")
    aid2 = make_article_id("hackernews", "https://example.com/c4")

    cid = get_or_create_concept(test_db, "rlhf", commit=False)
    link_article_concept(test_db, aid1, cid, commit=False)
    link_article_concept(test_db, aid2, cid, commit=False)
    record_read(test_db, aid1, commit=True)
    record_read(test_db, aid2, commit=True)

    result = get_recommendations_cluster(test_db, 2)
    assert result == []  # Both read, nothing to recommend
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_recommend_v08.py -v`
Expected: 3 PASS

- [ ] **Step 3: Update /api/recommend to use cluster + fallback**

In `D:\Projects\ai-news-digest\web\routes\api.py`, update the import to add `get_recommendations_cluster`:

```python
from db.models import (
    ..., get_recommendations_interest, get_recommendations_cluster, get_recent_articles,
)
```

Update the `recommend` endpoint:

```python
@router.get("/api/recommend/{article_id}")
@limiter.limit("10/minute")
async def recommend(article_id: str, request: Request = None):
    db = get_db()
    if db is None:
        return HTMLResponse("")

    interest = get_recommendations_interest(db, article_id, limit=2)
    cluster = get_recommendations_cluster(db, limit=2)

    seen = set()
    merged = []
    for r in interest + cluster:
        if r["id"] not in seen and r["id"] != article_id:
            seen.add(r["id"])
            merged.append(r)
        if len(merged) >= 4:
            break

    # Fallback: if not enough recommendations, fill with recent articles
    if len(merged) < 2:
        recents = get_recent_articles(db, article_id, exclude_read=True,
                                       limit=4 - len(merged))
        for r in recents:
            if r["id"] not in seen:
                seen.add(r["id"])
                merged.append({"id": r["id"], "title": r["title"],
                               "source_id": r["source_id"], "reason": "热门文章"})

    if not merged:
        return HTMLResponse("")

    cards = ""
    for r in merged:
        cards += (
            f'<div style="padding:8px 12px;margin:4px 0;background:var(--surface);border-radius:4px;'
            f'border-left:3px solid #2196f3;">'
            f'<a href="/reader/{r["id"]}" style="font-weight:500;">{r["title"]}</a>'
            f'<span style="color:#888;font-size:0.8em;margin-left:8px;">{r["source_id"]}</span>'
            f'<div style="color:#9c27b0;font-size:0.8em;margin-top:2px;">{r["reason"]}</div>'
            f'</div>'
        )
    return HTMLResponse(
        f'<div style="margin:24px 0;">'
        f'<h4 style="margin-bottom:8px;">推荐阅读</h4>{cards}</div>'
    )
```

- [ ] **Step 4: Add API-level test**

Add to `tests/test_recommend_v08.py`:

```python
import pytest
import os, tempfile
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals
from web.routes import api
from db.schema import init_db


@pytest.fixture
def client():
    tmp = os.path.join(tempfile.gettempdir(), "test_recommend_v08_api.db")
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


def test_recommend_endpoint_no_data_returns_empty(client):
    resp = client.get("/api/recommend/nonexistent")
    assert resp.status_code == 200
    assert resp.text == ""


def test_recommend_endpoint_fallback_to_recent(client):
    from web.globals import get_db
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("rec-fb-1", "hackernews", "https://example.com/fb1", "Fallback Article")
    )
    db.commit()
    resp = client.get("/api/recommend/rec-fb-1")
    assert resp.status_code == 200
    assert "Fallback Article" in resp.text
    assert "热门文章" in resp.text
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_recommend_v08.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add db/models.py web/routes/api.py tests/test_recommend_v08.py
git commit -m "feat: cluster-based recommendations — recent topic analysis replaces knowledge gap, with fallback"
```

---

### Task 3: 周报数据驱动

**Files:**
- Modify: `D:\Projects\ai-news-digest\db\models.py` — 新增 `get_weekly_hot_concepts`, `get_weekly_growing_concepts`
- Modify: `D:\Projects\ai-news-digest\orchestrator.py` — `generate_weekly_review` 注入统计数据
- Create: `D:\Projects\ai-news-digest\tests\test_weekly_v08.py`

- [ ] **Step 1: Add get_recent_articles + weekly stat queries to db/models.py**

Append to `D:\Projects\ai-news-digest\db\models.py`:

```python
def get_recent_articles(conn, exclude_id: str, exclude_read: bool = True,
                        limit: int = 4) -> list[dict]:
    """Fallback: return recent unread articles when recommendation engines are empty."""
    if exclude_read:
        rows = conn.execute(
            "SELECT id, title, source_id FROM articles "
            "WHERE id != ? AND id NOT IN (SELECT article_id FROM read_records) "
            "ORDER BY fetched_at DESC LIMIT ?",
            (exclude_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, title, source_id FROM articles "
            "WHERE id != ? ORDER BY fetched_at DESC LIMIT ?",
            (exclude_id, limit)
        ).fetchall()
    return [{"id": r[0], "title": r[1], "source_id": r[2]} for r in rows]


def _get_weekly_concepts_by_date(conn, week_start: str, date_column: str,
                                  limit: int) -> list[dict]:
    """Unified query: get concepts filtered by a date column >= week_start."""
    # Validate date format to prevent SQL injection via column name
    assert date_column in ("last_seen", "first_seen"), f"Invalid date column: {date_column}"
    assert isinstance(week_start, str) and len(week_start) == 10, \
        f"Invalid week_start format: {week_start}"
    rows = conn.execute(
        f"SELECT term, query_count FROM concepts "
        f"WHERE {date_column} >= ? "
        f"ORDER BY query_count DESC LIMIT ?",
        (week_start, limit)
    ).fetchall()
    return [{"term": r[0], "count": r[1]} for r in rows]


def get_weekly_hot_concepts(conn, week_start: str, limit: int = 5) -> list[dict]:
    """Top concepts by query_count seen this week."""
    return _get_weekly_concepts_by_date(conn, week_start, "last_seen", limit)


def get_weekly_growing_concepts(conn, week_start: str, limit: int = 3) -> list[dict]:
    """New concepts created this week, ordered by query_count."""
    return _get_weekly_concepts_by_date(conn, week_start, "first_seen", limit)
```

- [ ] **Step 2: Write tests for weekly stat queries**

Create `D:\Projects\ai-news-digest\tests\test_weekly_v08.py`:

```python
def test_weekly_hot_concepts(test_db):
    from db.models import get_weekly_hot_concepts
    from datetime import date
    today = date.today().isoformat()
    test_db.execute(
        "INSERT OR IGNORE INTO concepts (term, query_count, last_seen) VALUES (?, ?, ?)",
        ("transformer", 15, today)
    )
    test_db.execute(
        "INSERT OR IGNORE INTO concepts (term, query_count, last_seen) VALUES (?, ?, ?)",
        ("agent", 12, "2020-01-01")
    )
    test_db.commit()
    hot = get_weekly_hot_concepts(test_db, today)
    assert len(hot) == 1
    assert hot[0]["term"] == "transformer"


def test_weekly_growing_concepts(test_db):
    from db.models import get_weekly_growing_concepts
    from datetime import date
    today = date.today().isoformat()
    test_db.execute(
        "INSERT OR IGNORE INTO concepts (term, query_count, first_seen, definition) VALUES (?, ?, ?, ?)",
        ("tool-use", 5, today, "")
    )
    test_db.commit()
    growing = get_weekly_growing_concepts(test_db, today)
    assert len(growing) == 1
    assert growing[0]["term"] == "tool-use"


def test_weekly_date_format_validation():
    import pytest
    from db.models import _get_weekly_concepts_by_date
    with pytest.raises(AssertionError):
        _get_weekly_concepts_by_date(None, "bad", "invalid_column", 5)
    with pytest.raises(AssertionError):
        _get_weekly_concepts_by_date(None, "not-a-date", "last_seen", 5)


def test_get_recent_articles(test_db):
    from db.models import get_recent_articles
    test_db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("ra-1", "hackernews", "https://example.com/ra1", "Recent 1")
    )
    test_db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("ra-2", "jiqizhixin", "https://example.com/ra2", "Recent 2")
    )
    test_db.commit()
    result = get_recent_articles(test_db, "ra-1", exclude_read=False, limit=1)
    assert len(result) == 1
    assert result[0]["id"] == "ra-2"


def test_weekly_stats_empty(test_db):
    from db.models import get_weekly_hot_concepts, get_weekly_growing_concepts
    assert get_weekly_hot_concepts(test_db, "2099-01-01") == []
    assert get_weekly_growing_concepts(test_db, "2099-01-01") == []
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_weekly_v08.py -v`
Expected: 3 PASS

- [ ] **Step 3: Update generate_weekly_review in orchestrator.py**

In `D:\Projects\ai-news-digest\orchestrator.py`, find the `generate_weekly_review` function. After the `from db.models import get_concepts_list, get_recommendations_gap` imports inside the function, update to also import the new stat functions. Replace the Markdown building section:

Find:
```python
    from db.models import get_concepts_list, get_recommendations_gap
    top_concepts = get_concepts_list(db_conn, limit=5)
    top_concept_str = ", ".join(c["term"] for c in top_concepts) or "暂无数据"
    recs = get_recommendations_gap(db_conn, limit=3)
```

Replace with:
```python
    from db.models import (get_concepts_list, get_recommendations_cluster,
                           get_weekly_hot_concepts, get_weekly_growing_concepts)

    hot = get_weekly_hot_concepts(db_conn, week_start, limit=5)
    hot_str = ", ".join(f"{c['term']} ({c['count']}次)" for c in hot) or "暂无数据"

    growing = get_weekly_growing_concepts(db_conn, week_start, limit=3)
    growing_str = ", ".join(f"{c['term']} ({c['count']}次)" for c in growing) or "暂无数据"

    recs = get_recommendations_cluster(db_conn, limit=3)
```

Then update the MD template section. Find:
```python
## 本周热词
{top_concept_str}
```

Replace with:
```python
## 本周热词
{hot_str}

## 新晋概念
{growing_str}
```

- [ ] **Step 4: Add test for MD template with stats**

Add to `tests/test_weekly_v08.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


def test_generate_weekly_review_with_stats(test_db):
    from orchestrator import generate_weekly_review
    from config import Config

    cfg = Config(
        deepseek_api_key="sk-test",
        wecom_webhook_url="",
        exploration_rate=0.0,
        cluster_threshold=0.6,
        max_daily_articles=20,
        host="127.0.0.1",
        port=8765,
        full_text_retention_days=90,
        analysis_cache_retention_days=180,
    )

    mock_ai = MagicMock()
    mock_ai.chat.return_value = ("本周你阅读了文章。", 100)

    with patch('orchestrator.get_read_articles_with_insights', return_value=[
        {"title": "Test", "insight": "AI stuff"}
    ]), patch('orchestrator.get_concepts_list', return_value=[
        {"term": "transformer", "definition": "", "query_count": 5}
    ]), patch('orchestrator.get_feedback_articles', return_value=[]), \
         patch('orchestrator.get_read_article_ids_since', return_value=["art1"]), \
         patch('orchestrator.get_weekly_hot_concepts', return_value=[
             {"term": "agent", "count": 12}
         ]), \
         patch('orchestrator.get_weekly_growing_concepts', return_value=[
             {"term": "tool-use", "count": 5}
         ]), \
         patch('orchestrator.get_recommendations_cluster', return_value=[]):

        result = generate_weekly_review(test_db, mock_ai, cfg)
        assert result is not None
        assert result["status"] == "ok"
        assert "## 新晋概念" in result["content"]
        assert "agent (12次)" in result["content"]
        assert "tool-use (5次)" in result["content"]
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_weekly_v08.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add db/models.py orchestrator.py tests/test_weekly_v08.py
git commit -m "feat: data-driven weekly review — hot concepts + growing concepts stats in MD template"
```

---

### Task 4: 集成验证 + 全量回归

**Files:**
- No new files — integration verification

- [ ] **Step 1: Run full test suite**

```
.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```
Expected: 210+ tests pass

- [ ] **Step 2: Run coverage**

```
.venv\Scripts\python.exe -m pytest tests/ --cov --cov-report=term -q
```
Expected: coverage >= 83%

- [ ] **Step 3: Verify specific v0.8 behaviors**
- [ ] graph_snapshots table exists with UNIQUE(snap_date, period)
- [ ] /graph?compare=DATE loads snapshot data
- [ ] /graph hides compare dropdown when no snapshots exist
- [ ] /api/recommend uses cluster engine (reason starts with "近期关注")
- [ ] /api/recommend falls back to recent articles when no cluster data
- [ ] generate_weekly_review includes "本周热词" and "新晋概念" sections

- [ ] **Step 4: Commit**

```bash
git commit -m "test: v0.8 integration verification — 210+ tests, coverage >=83%" --allow-empty
```

---

## Final Integration

After all 4 tasks complete:
```
.venv\Scripts\python.exe -m pytest tests/ -v --cov --tb=short
```
Expected: 210+ tests pass, coverage >= 83%
