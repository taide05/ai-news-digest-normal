# AI 资讯管家 v0.7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从"理解单篇文章"升级到"建立个人知识网络" — 概念自动提取 + 概念关联图 + 双引擎推荐 + Markdown 周刊自动推送

**Architecture:** 概念提取是数据基础（复用 analysis_cache），关联图和推荐在概念数据上构建，周刊独立并行。新增 1 个路由模块(graph.py) + 1 个模板(graph.html)，其他在现有文件上增量。

**Tech Stack:** Python 3.13, FastAPI, SQLite WAL, Jinja2 + htmx, APScheduler, PushChannel

---

### Task 1: 概念自动提取 — Prompt + API + 前端触发

**Files:**
- Modify: `D:\Projects\ai-news-digest\ai\analysis.py` — 新增 `build_concept_extraction_prompt`
- Modify: `D:\Projects\ai-news-digest\web\routes\api.py` — 新增 `/api/auto-extract-concepts/{article_id}`
- Modify: `D:\Projects\ai-news-digest\web\templates\reader.html` — htmx 自动触发
- Create: `D:\Projects\ai-news-digest\tests\test_concept_extract.py`

- [ ] **Step 1: Add build_concept_extraction_prompt to ai/analysis.py**

In `ai/analysis.py`, append after `build_cross_comparison_prompt`:

```python
def build_concept_extraction_prompt(full_text: str) -> tuple[str, str]:
    system = "你是一个技术术语提取助手。只输出术语，不要解释。"
    user = f"""从以下文章中提取最多 5 个 AI/技术领域的关键概念术语。
只输出逗号分隔的术语列表，不要解释。
如果文章不包含值得提取的概念，输出"无"。

文章：
{_truncate(full_text, 4000)}"""
    return system, user
```

- [ ] **Step 2: Write tests for the prompt**

In `tests/test_concept_extract.py`:

```python
def test_concept_extraction_prompt_format():
    from ai.analysis import build_concept_extraction_prompt
    system, user = build_concept_extraction_prompt("Transformer models use attention mechanisms.")
    assert "最多 5 个" in user
    assert "Transformer" in user
    assert "无" in user


def test_concept_extraction_prompt_long_text_truncated():
    from ai.analysis import build_concept_extraction_prompt
    long_text = "AI " * 5000
    system, user = build_concept_extraction_prompt(long_text)
    assert len(user) < 12000  # 4000 chars + prompt overhead
```

- [ ] **Step 3: Run tests to verify prompt**

```
.venv\Scripts\python.exe -m pytest tests/test_concept_extract.py -v
```
Expected: 2 PASS

- [ ] **Step 4: Add /api/auto-extract-concepts endpoint to api.py**

Add to `web/routes/api.py` after the concept-lookup endpoint. First update the import in `api.py` to add `build_concept_extraction_prompt`:

```python
from ai.analysis import (
    build_core_insight_prompt, build_what_it_means_prompt,
    build_translation_prompt, build_concept_lookup_prompt,
    build_cross_comparison_prompt, build_concept_extraction_prompt,
)
```

Then add the endpoint before `@router.post("/api/feedback/{article_id}")`:

```python
@router.get("/api/auto-extract-concepts/{article_id}")
@limiter.limit("10/minute")
async def auto_extract_concepts(article_id: str, request: Request = None):
    db = get_db()
    if db is None:
        return JSONResponse({"concepts": [], "new": False})

    # Check cache
    cached = get_cached_analysis(db, article_id, "concepts")
    if cached:
        return JSONResponse({"concepts": json.loads(cached), "new": False})

    article = get_article(db, article_id)
    if article is None:
        return JSONResponse({"concepts": [], "new": False})

    full_text = article.get("full_text") or article.get("content") or ""
    if not full_text or full_text in _EXTRACTION_ERROR_SET:
        return JSONResponse({"concepts": [], "new": False})

    ai = get_ai()
    if ai is None:
        return JSONResponse({"concepts": [], "new": False})

    system, user = build_concept_extraction_prompt(full_text)
    try:
        raw, tokens = ai.chat(system, user, max_tokens=100)
    except Exception as e:
        logger.warning("Concept extraction failed for article %s: %s", article_id, e)
        return JSONResponse({"concepts": [], "new": False})

    raw = raw.strip().strip('"').strip("'")
    if raw == "无" or not raw:
        cache_analysis(db, article_id, "concepts", "[]", tokens_used=tokens)
        return JSONResponse({"concepts": [], "new": False})

    terms = [t.strip() for t in raw.split(",") if t.strip()]
    new_terms = []
    for term in terms:
        cid = get_or_create_concept(db, term, commit=False)
        link_article_concept(db, article_id, cid, commit=False)
        new_terms.append(term)
    db.commit()

    concepts_json = json.dumps(new_terms)
    cache_analysis(db, article_id, "concepts", concepts_json, tokens_used=tokens)

    return JSONResponse({"concepts": new_terms, "new": True})
```

- [ ] **Step 5: Add htmx trigger to reader.html**

In `web/templates/reader.html`, after the core-insight div (which uses `hx-trigger="load"`), add a hidden trigger that fires when core_insight SSE completes. Insert after line 48 (the closing `</div>` of core-insight):

```html
<div hx-get="/api/auto-extract-concepts/{{ article.id }}"
     hx-trigger="load delay:2s"
     hx-target="#concept-tags" hx-swap="innerHTML">
</div>
<div id="concept-tags" style="margin:8px 0;"></div>
```

- [ ] **Step 6: Add test for the API endpoint**

In `tests/test_concept_extract.py`, add:

```python
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
    data = resp.json()
    assert isinstance(data["concepts"], list)


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
    data = resp.json()
    assert data["new"] is False
    assert "RL" in data["concepts"]
```

- [ ] **Step 7: Run concept extraction tests**

```
.venv\Scripts\python.exe -m pytest tests/test_concept_extract.py -v
```
Expected: 4 PASS

- [ ] **Step 8: Commit**

```bash
git add ai/analysis.py web/routes/api.py web/templates/reader.html tests/test_concept_extract.py
git commit -m "feat: auto concept extraction — AI scans article for terms, caches result, htmx triggers on reader page"
```

---

### Task 2: 资讯关联图页面

**Files:**
- Create: `D:\Projects\ai-news-digest\web\routes\graph.py`
- Create: `D:\Projects\ai-news-digest\web\templates\graph.html`
- Modify: `D:\Projects\ai-news-digest\web\app.py` — 注册 graph router
- Modify: `D:\Projects\ai-news-digest\web\templates\home.html` — 底部导航加 `/graph`
- Modify: `D:\Projects\ai-news-digest\web\templates\reader.html` — 底部导航加 `/graph`
- Modify: `D:\Projects\ai-news-digest\db\models.py` — 新增 `get_graph_data`
- Create: `D:\Projects\ai-news-digest\tests\test_graph.py`

- [ ] **Step 1: Add get_graph_data to db/models.py**

```python
def get_graph_data(conn, period: str = "today") -> list[dict]:
    """Return concept-article relations for the graph page.
    period: 'today' or 'week'.
    """
    if period == "today":
        date_filter = "date('now')"
    else:
        date_filter = "date('now', '-7 days')"

    rows = conn.execute(
        "SELECT a.id, a.title, a.source_id, c.term, c.query_count "
        "FROM articles a "
        "JOIN article_concepts ac ON a.id = ac.article_id "
        "JOIN concepts c ON ac.concept_id = c.id "
        "WHERE a.fetched_at >= " + date_filter + " "
        "ORDER BY c.query_count DESC LIMIT 100",
    ).fetchall()
    return [{"article_id": r[0], "title": r[1], "source_id": r[2],
             "concept": r[3], "query_count": r[4]} for r in rows]
```

Note: the `+ date_filter` uses string concatenation because SQLite parameterized queries don't support function calls in WHERE clauses. The `date_filter` values are hardcoded constants, not user input — safe from SQL injection.

- [ ] **Step 2: Write test for get_graph_data**

In `tests/test_graph.py`:

```python
def test_get_graph_data_empty(test_db):
    from db.models import get_graph_data
    rows = get_graph_data(test_db, "today")
    assert rows == []


def test_get_graph_data_with_data(test_db):
    from db.models import get_graph_data, get_or_create_concept, link_article_concept
    test_db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("g-art-1", "hackernews", "https://example.com/g1", "Graph Article")
    )
    test_db.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("g-art-2", "jiqizhixin", "https://example.com/g2", "Graph Article 2")
    )
    cid = get_or_create_concept(test_db, "transformer", commit=False)
    link_article_concept(test_db, "g-art-1", cid, commit=False)
    link_article_concept(test_db, "g-art-2", cid, commit=False)
    test_db.commit()
    rows = get_graph_data(test_db, "today")
    assert len(rows) == 2
    assert rows[0]["concept"] == "transformer"
```

- [ ] **Step 3: Run graph model tests**

```
.venv\Scripts\python.exe -m pytest tests/test_graph.py -v
```
Expected: 2 PASS

- [ ] **Step 4: Create web/routes/graph.py**

```python
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from web.globals import get_db
from db.models import get_graph_data
from web.templates import templates

router = APIRouter()


@router.get("/graph", response_class=HTMLResponse)
async def graph(request: Request, period: str = Query("today")):
    db = get_db()
    nodes = []
    edges = []
    if db:
        rows = get_graph_data(db, period)
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

    return templates.TemplateResponse(request, "graph.html", {
        "nodes": nodes, "edges": edges, "period": period,
        "node_count": len(nodes), "edge_count": len(edges),
    })
```

- [ ] **Step 5: Register graph router in web/app.py**

In `web/app.py`, add to imports:
```python
from .routes import home, reader, search, concepts, review, sources, export, graph, api
```

Add to `create_app()` after the export router:
```python
app_.include_router(graph.router)
```

- [ ] **Step 6: Create web/templates/graph.html**

```html
{% extends "base.html" %}
{% block content %}
<h1>资讯关联图</h1>

<div style="margin-bottom:12px;">
    <a href="/graph?period=today" class="btn" style="{% if period=='today' %}font-weight:bold;{% endif %}">今天</a>
    <a href="/graph?period=week" class="btn" style="{% if period=='week' %}font-weight:bold;{% endif %}">本周</a>
</div>

{% if nodes|length == 0 %}
<div class="empty-state">
    <p>{{ '今天' if period=='today' else '本周' }}还没有已分析的文章。先阅读几篇带概念的文章吧。</p>
</div>
{% else %}
<div style="text-align:center;color:#888;margin-bottom:8px;">
    {{ node_count }} 个节点 · {{ edge_count }} 条边
</div>

<svg id="graph-svg" width="100%" height="500" style="background:var(--surface);border-radius:8px;"></svg>
{% endif %}

<nav class="bottom-nav">
    <a href="/">首页</a>
    <a href="/sources">信息源</a>
    <a href="/search">搜索</a>
    <a href="/concepts">概念词典</a>
    <a href="/review">周报</a>
</nav>

<script>
{% if nodes|length > 0 %}
(function(){
    var nodes = {{ nodes | tojson }};
    var edges = {{ edges | tojson }};
    var svg = document.getElementById('graph-svg');
    var width = svg.clientWidth || 800;
    var height = 500;

    // Simplified force-directed layout
    var positions = {};
    var R = 8;
    nodes.forEach(function(n) {
        positions[n.id] = {
            x: Math.random() * (width - 100) + 50,
            y: Math.random() * (height - 100) + 50,
            vx: 0, vy: 0
        };
    });

    for (var iter = 0; iter < 50; iter++) {
        // Repulsion between all nodes
        var ids = Object.keys(positions);
        for (var i = 0; i < ids.length; i++) {
            for (var j = i + 1; j < ids.length; j++) {
                var a = positions[ids[i]];
                var b = positions[ids[j]];
                var dx = a.x - b.x;
                var dy = a.y - b.y;
                var dist = Math.sqrt(dx * dx + dy * dy) || 1;
                var force = 500 / (dist * dist);
                a.vx += (dx / dist) * force;
                a.vy += (dy / dist) * force;
                b.vx -= (dx / dist) * force;
                b.vy -= (dy / dist) * force;
            }
        }
        // Attraction along edges
        edges.forEach(function(e) {
            var a = positions[e.from];
            var b = positions[e.to];
            if (!a || !b) return;
            var dx = b.x - a.x;
            var dy = b.y - a.y;
            var dist = Math.sqrt(dx * dx + dy * dy) || 1;
            var force = dist * 0.01;
            a.vx += (dx / dist) * force;
            a.vy += (dy / dist) * force;
            b.vx -= (dx / dist) * force;
            b.vy -= (dy / dist) * force;
        });
        // Apply velocities with damping
        ids.forEach(function(id) {
            var p = positions[id];
            p.x += p.vx * 0.5;
            p.y += p.vy * 0.5;
            p.x = Math.max(R, Math.min(width - R, p.x));
            p.y = Math.max(R, Math.min(height - R, p.y));
            p.vx *= 0.9;
            p.vy *= 0.9;
        });
    }

    // Draw edges
    edges.forEach(function(e) {
        var a = positions[e.from];
        var b = positions[e.to];
        if (!a || !b) return;
        var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
        line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
        line.setAttribute('stroke', '#555'); line.setAttribute('stroke-width', '0.5');
        line.setAttribute('opacity', '0.4');
        svg.appendChild(line);
    });

    // Draw nodes
    nodes.forEach(function(n) {
        var p = positions[n.id];
        var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', p.x); circle.setAttribute('cy', p.y);
        var r = n.type === 'concept' ? Math.min(4 + n.query_count, 16) : 6;
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

        // Label
        var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', p.x + r + 2); text.setAttribute('y', p.y + 4);
        text.setAttribute('fill', '#ccc'); text.setAttribute('font-size', '10');
        text.setAttribute('font-family', 'sans-serif');
        text.textContent = n.label.substring(0, 15);
        svg.appendChild(text);
    });
})();
{% endif %}
</script>
{% endblock %}
```

- [ ] **Step 7: Add /graph to bottom navigation in home.html and reader.html**

In `web/templates/home.html`, in the `bottom-nav` div, add before the closing `</nav>`:
```html
    <a href="/graph">关联图</a>
```

In `web/templates/reader.html`, in the `bottom-nav` div, add before the closing `</nav>`:
```html
    <a href="/graph">关联图</a>
```

- [ ] **Step 8: Write test for graph page**

In `tests/test_graph.py`, add:

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
    tmp = os.path.join(tempfile.gettempdir(), "test_graph.db")
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


def test_graph_page_loads_empty(client):
    resp = client.get("/graph")
    assert resp.status_code == 200
    assert "还没有" in resp.text


def test_graph_page_loads_today(client):
    resp = client.get("/graph?period=today")
    assert resp.status_code == 200


def test_graph_page_loads_week(client):
    resp = client.get("/graph?period=week")
    assert resp.status_code == 200
```

- [ ] **Step 9: Run graph tests**

```
.venv\Scripts\python.exe -m pytest tests/test_graph.py -v
```
Expected: 5 PASS

- [ ] **Step 10: Commit**

```bash
git add web/routes/graph.py web/templates/graph.html web/app.py web/templates/home.html web/templates/reader.html db/models.py tests/test_graph.py
git commit -m "feat: concept graph page — force-directed SVG, today/week toggle, article-concept edges"
```

---

### Task 3: 双引擎阅读推荐

**Files:**
- Modify: `D:\Projects\ai-news-digest\web\routes\api.py` — 新增 `/api/recommend/{article_id}`
- Modify: `D:\Projects\ai-news-digest\web\templates\reader.html` — 推荐区块
- Modify: `D:\Projects\ai-news-digest\db\models.py` — 新增推荐查询函数
- Create: `D:\Projects\ai-news-digest\tests\test_recommend.py`

- [ ] **Step 1: Add recommendation query functions to db/models.py**

```python
def get_recommendations_interest(conn, article_id: str, limit: int = 2) -> list[dict]:
    """Engine A: Find articles sharing concepts with the current article,
    prioritizing concepts matching user's interested topics."""
    rows = conn.execute(
        "SELECT DISTINCT a.id, a.title, a.source_id "
        "FROM articles a "
        "JOIN article_concepts ac ON a.id = ac.article_id "
        "WHERE ac.concept_id IN ("
        "  SELECT concept_id FROM article_concepts WHERE article_id = ?"
        ") AND a.id != ? "
        "AND a.id NOT IN (SELECT article_id FROM read_records) "
        "LIMIT ?",
        (article_id, article_id, limit)
    ).fetchall()
    return [{"id": r[0], "title": r[1], "source_id": r[2],
             "reason": "相似内容"} for r in rows]


def get_recommendations_gap(conn, limit: int = 2) -> list[dict]:
    """Engine B: Find articles about popular concepts the user hasn't read about."""
    rows = conn.execute(
        "SELECT DISTINCT a.id, a.title, a.source_id, c.term "
        "FROM articles a "
        "JOIN article_concepts ac ON a.id = ac.article_id "
        "JOIN concepts c ON ac.concept_id = c.id "
        "WHERE c.id IN ("
        "  SELECT id FROM concepts ORDER BY query_count DESC LIMIT 20"
        ") "
        "AND c.id NOT IN ("
        "  SELECT DISTINCT ac2.concept_id FROM article_concepts ac2 "
        "  JOIN read_records rr ON ac2.article_id = rr.article_id"
        ") "
        "AND a.id NOT IN (SELECT article_id FROM read_records) "
        "ORDER BY c.query_count DESC, a.fetched_at DESC "
        "LIMIT ?",
        (limit,)
    ).fetchall()
    return [{"id": r[0], "title": r[1], "source_id": r[2],
             "reason": f"探索「{r[3]}」"} for r in rows]
```

- [ ] **Step 2: Write tests for recommendation queries**

In `tests/test_recommend.py`:

```python
def test_recommendations_empty(test_db):
    from db.models import get_recommendations_interest, get_recommendations_gap
    assert get_recommendations_interest(test_db, "nonexistent", 2) == []
    assert get_recommendations_gap(test_db, 2) == []


def test_recommendations_interest_finds_similar(test_db):
    from db.models import (get_recommendations_interest,
                           get_or_create_concept, link_article_concept,
                           insert_article)
    # Create two articles sharing a concept
    insert_article(test_db, "hackernews", "https://example.com/r1", "Article 1", commit=False)
    insert_article(test_db, "hackernews", "https://example.com/r2", "Article 2", commit=False)
    from db.url_utils import make_article_id
    aid1 = make_article_id("hackernews", "https://example.com/r1")
    aid2 = make_article_id("hackernews", "https://example.com/r2")
    cid = get_or_create_concept(test_db, "transformer", commit=False)
    link_article_concept(test_db, aid1, cid, commit=False)
    link_article_concept(test_db, aid2, cid, commit=False)
    test_db.commit()
    results = get_recommendations_interest(test_db, aid1, 2)
    assert len(results) == 1
    assert results[0]["id"] == aid2


def test_recommendations_excludes_read(test_db):
    from db.models import get_recommendations_interest, insert_article, record_read
    from db.models import get_or_create_concept, link_article_concept
    from db.url_utils import make_article_id
    insert_article(test_db, "hackernews", "https://example.com/r3", "Article 3", commit=False)
    insert_article(test_db, "hackernews", "https://example.com/r4", "Article 4", commit=False)
    aid3 = make_article_id("hackernews", "https://example.com/r3")
    aid4 = make_article_id("hackernews", "https://example.com/r4")
    cid = get_or_create_concept(test_db, "rlhf", commit=False)
    link_article_concept(test_db, aid3, cid, commit=False)
    link_article_concept(test_db, aid4, cid, commit=False)
    record_read(test_db, aid4, commit=True)
    results = get_recommendations_interest(test_db, aid3, 2)
    assert len(results) == 0  # aid4 excluded because already read
```

- [ ] **Step 3: Run recommendation model tests**

```
.venv\Scripts\python.exe -m pytest tests/test_recommend.py -v
```
Expected: 3 PASS

- [ ] **Step 4: Add /api/recommend/{article_id} endpoint to api.py**

Add to `web/routes/api.py` after the auto-extract-concepts endpoint. Update imports to add:
```python
from db.models import (
    ..., get_recommendations_interest, get_recommendations_gap,
)
```

Then add the endpoint:

```python
@router.get("/api/recommend/{article_id}")
@limiter.limit("10/minute")
async def recommend(article_id: str, request: Request = None):
    db = get_db()
    if db is None:
        return JSONResponse({"recommendations": []})

    interest = get_recommendations_interest(db, article_id, limit=2)
    gap = get_recommendations_gap(db, limit=2)

    seen = set()
    merged = []
    for r in interest + gap:
        if r["id"] not in seen and r["id"] != article_id:
            seen.add(r["id"])
            merged.append(r)
        if len(merged) >= 4:
            break

    return JSONResponse({"recommendations": merged})
```

- [ ] **Step 5: Add recommendation block to reader.html**

In `web/templates/reader.html`, after the feedback-bar div (after line ~86), add:

```html
<div hx-get="/api/recommend/{{ article.id }}"
     hx-trigger="load delay:3s"
     hx-target="#recommend-block" hx-swap="innerHTML">
</div>
<div id="recommend-block" style="margin:24px 0;"></div>
```

- [ ] **Step 6: Add API test for recommend endpoint**

In `tests/test_recommend.py`, add:

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
    tmp = os.path.join(tempfile.gettempdir(), "test_recommend_api.db")
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


def test_recommend_endpoint_no_data(client):
    resp = client.get("/api/recommend/nonexistent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["recommendations"] == []
```

- [ ] **Step 7: Run all recommend tests**

```
.venv\Scripts\python.exe -m pytest tests/test_recommend.py -v
```
Expected: 4 PASS

- [ ] **Step 8: Commit**

```bash
git add web/routes/api.py web/templates/reader.html db/models.py tests/test_recommend.py
git commit -m "feat: dual-engine reading recommendations — interest + knowledge gap, merged top 4"
```

---

### Task 4: Markdown 周刊自动推送

**Files:**
- Modify: `D:\Projects\ai-news-digest\orchestrator.py` — MD 渲染 + 推送集成
- Modify: `D:\Projects\ai-news-digest\scheduler.py` — 独立周报定时任务
- Create: `D:\Projects\ai-news-digest\tests\test_md_weekly.py`

- [ ] **Step 1: Modify generate_weekly_review to produce Markdown format**

In `orchestrator.py`, update `generate_weekly_review` to include top concepts and recommendations in the review content. After the line `content, tokens = ai_client.chat(system, user, max_tokens=2048)`, add:

```python
    # Build Markdown with top concepts and recommendations
    from db.models import get_concepts_list, get_recommendations_gap
    top_concepts = get_concepts_list(db_conn, limit=5)
    top_concept_str = ", ".join(c["term"] for c in top_concepts)
    recs = get_recommendations_gap(db_conn, limit=3)
    rec_lines = "\n".join(f"- [{r['title']}](/reader/{r['id']})" for r in recs) or "暂无推荐"

    md_content = f"""# AI 资讯周刊 — {week_start} ~ {week_end}

## 本周概览
{content}

## 本周热词
{top_concept_str}

## 推荐阅读
{rec_lines}

---
由 AI 资讯管家自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}"""

    article_ids = get_read_article_ids_since(db_conn, since)
    save_weekly_review(db_conn, week_start, week_end, md_content, article_ids)

    return {"status": "ok", "content": md_content, "week_start": week_start, "week_end": week_end}
```

The key change: save `md_content` instead of raw `content`; include top concepts and recs; full Markdown formatting.

- [ ] **Step 2: Add weekly_md job to scheduler.py**

In `scheduler.py`, add a new job after the daily_job. Insert after the `_scheduler.add_job(...)` block for daily_collection:

```python
    # Weekly Markdown review: Monday 8:00 AM
    try:
        _scheduler.add_job(
            weekly_md_job,
            CronTrigger.from_crontab("0 8 * * 1", timezone='Asia/Shanghai'),
            id='weekly_md_review',
            name='Weekly Markdown review generation and push',
            replace_existing=True,
        )
    except Exception as e:
        logger.warning(f"Could not add weekly_md job: {e}")
```

And add the `weekly_md_job` function before `create_scheduler`:

```python
def _weekly_md_job(db_conn, cfg, orchestrator_module):
    """Generate and push weekly Markdown review."""
    import asyncio
    from ai.client import AIClient

    async def _run():
        ai_client = None
        if cfg.deepseek_api_key:
            ai_client = AIClient(cfg.deepseek_api_key)
        if not ai_client:
            logger.warning("Weekly MD: No AI client available")
            return
        result = orchestrator_module.generate_weekly_review(db_conn, ai_client, cfg)
        if result and result.get("status") == "ok":
            pushed = await orchestrator_module.push_weekly_review(db_conn, cfg)
            logger.info(f"Weekly MD: generated and pushed={pushed}")

    asyncio.run(_run())
```

Note: This function must be defined BEFORE `create_scheduler` since it's referenced inside `create_scheduler`. Add it between the `_scheduler = None` line and the `create_scheduler` function.

- [ ] **Step 3: Update scheduler.py create_scheduler to capture references**

The `_weekly_md_job` needs access to db_conn, cfg, orchestrator_module. These are already stored on the scheduler object. Update the `weekly_md_job` wrapper in `create_scheduler` after the existing daily_job definition:

```python
    def weekly_md_wrapper():
        _weekly_md_job(db_conn, cfg, orchestrator_module)
```

- [ ] **Step 4: Write test for Markdown format**

In `tests/test_md_weekly.py`:

```python
def test_weekly_review_has_markdown_format(test_db):
    """Verify generate_weekly_review returns Markdown content when AI is available."""
    from orchestrator import generate_weekly_review
    from config import Config
    # Without AI client, should return None (no articles read)
    cfg = Config(
        deepseek_api_key="",
        wecom_webhook_url="",
        exploration_rate=0.0,
        cluster_threshold=0.6,
        max_daily_articles=20,
        host="127.0.0.1",
        port=8765,
        full_text_retention_days=90,
        analysis_cache_retention_days=180,
    )
    result = generate_weekly_review(test_db, None, cfg)
    assert result is None  # No AI, no data


def test_push_weekly_review_no_existing_review(test_db):
    """push_weekly_review returns False when no review exists."""
    import asyncio
    from orchestrator import push_weekly_review
    from config import Config
    cfg = Config(
        deepseek_api_key="",
        wecom_webhook_url="",
        exploration_rate=0.0,
        cluster_threshold=0.6,
        max_daily_articles=20,
        host="127.0.0.1",
        port=8765,
        full_text_retention_days=90,
        analysis_cache_retention_days=180,
    )
    result = asyncio.run(push_weekly_review(test_db, cfg))
    assert result is False
```

- [ ] **Step 5: Run MD weekly tests**

```
.venv\Scripts\python.exe -m pytest tests/test_md_weekly.py -v
```
Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add orchestrator.py scheduler.py tests/test_md_weekly.py
git commit -m "feat: markdown weekly review — auto-generate .md with concepts + recs, scheduled push on Monday"
```

---

### Task 5: 集成验证 + 全量回归

**Files:**
- No new files — integration verification

- [ ] **Step 1: Run full test suite**

```
.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```
Expected: 195+ tests pass

- [ ] **Step 2: Run coverage**

```
.venv\Scripts\python.exe -m pytest tests/ --cov --cov-report=term -q
```
Expected: coverage >= 82%

- [ ] **Step 3: Verify specific v0.7 behaviors**
- [ ] Concept extraction prompt includes "最多 5 个" and "无" fallback
- [ ] /api/auto-extract-concepts returns cached result on second call
- [ ] /graph page loads with today/week periods
- [ ] /api/recommend returns merged results from both engines
- [ ] generate_weekly_review produces Markdown format
- [ ] New bottom-nav links to /graph on all pages

- [ ] **Step 4: Commit**

```bash
git commit -m "test: v0.7 integration verification — 195+ tests, coverage >=82%" --allow-empty
```

---

## Final Integration

After all 5 tasks complete:
```
.venv\Scripts\python.exe -m pytest tests/ -v --cov --tb=short
```
Expected: 195+ tests pass, coverage >= 82%
