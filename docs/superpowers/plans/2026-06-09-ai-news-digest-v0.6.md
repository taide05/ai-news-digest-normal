# AI 资讯管家 v0.6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从"知道发生了什么"升级到"理解这意味着什么" — 5维深度分析 + 跨文章横向对比

**Architecture:** 重写 what_it_means prompt 为 5 维结构（吸收反方观点），新增 cross_analysis_cache 表支持跨文章对比，阅读页改为折叠式按需加载控制在认知预算内

**Tech Stack:** Python 3.13, FastAPI + uvicorn, SQLite WAL, Jinja2, htmx SSE, pytest

---

### Task 1: analysis_cache schema 扩展 + API dispatch 重构

**Files:**
- Modify: `D:\Projects\ai-news-digest\db\schema.py` — add cross_analysis_cache table
- Modify: `D:\Projects\ai-news-digest\web\routes\api.py` — if/elif → dispatch map
- Modify: `D:\Projects\ai-news-digest\db\models.py` — add cross-cache CRUD
- Create: `D:\Projects\ai-news-digest\tests\test_cross_cache.py`

- [ ] **Step 1: Add cross_analysis_cache table to SCHEMA_SQL**

In `db/schema.py`, add after analysis_cache table definition:

```sql
CREATE TABLE IF NOT EXISTS cross_analysis_cache (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id    TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    content       TEXT NOT NULL,
    article_ids   TEXT NOT NULL,
    model         TEXT DEFAULT 'deepseek-chat',
    tokens_used   INTEGER,
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(cluster_id, analysis_type)
);
```

- [ ] **Step 2: Add cross-cache CRUD to db/models.py**

```python
def cache_cross_analysis(conn, cluster_id: str, analysis_type: str, content: str,
                         article_ids: list[str], model: str = "deepseek-chat",
                         tokens_used: int = 0, commit: bool = True):
    import json
    ids_json = json.dumps(article_ids)
    try:
        conn.execute(
            "INSERT INTO cross_analysis_cache (cluster_id, analysis_type, content, article_ids, model, tokens_used) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cluster_id, analysis_type, content, ids_json, model, tokens_used)
        )
        if commit:
            conn.commit()
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE cross_analysis_cache SET content = ?, tokens_used = ? "
            "WHERE cluster_id = ? AND analysis_type = ?",
            (content, tokens_used, cluster_id, analysis_type)
        )
        if commit:
            conn.commit()


def get_cached_cross_analysis(conn, cluster_id: str, analysis_type: str) -> str | None:
    row = conn.execute(
        "SELECT content FROM cross_analysis_cache WHERE cluster_id = ? AND analysis_type = ?",
        (cluster_id, analysis_type)
    ).fetchone()
    return row[0] if row else None
```

- [ ] **Step 3: Refactor api.py analyze endpoint with dispatch map**

In `web/routes/api.py`, replace the if/elif chain in the `analyze` function (the part that selects prompt by type) with a dispatch map. Add it near the top of the module after imports:

```python
def _get_analyzer(ai, db, article_id: str, analysis_type: str, full_text: str):
    """Dispatch map for analysis types. Returns (system_prompt, user_prompt) or None."""
    if analysis_type == "core_insight":
        from ai.analysis import build_core_insight_prompt
        return build_core_insight_prompt(full_text)
    elif analysis_type == "what_it_means":
        from ai.analysis import build_what_it_means_prompt
        concepts = [c["term"] for c in get_concepts_list(db)]
        # v0.6: assemble user context for personal relevance dimension
        user_topics = _get_user_topics(db)
        read_titles = _get_recent_read_titles(db, limit=10)
        return build_what_it_means_prompt(full_text, concepts, user_topics, read_titles)
    else:
        return None


def _get_user_topics(db) -> list[str]:
    rows = db.execute(
        "SELECT DISTINCT topics FROM read_records WHERE topics != '' AND feedback = 'interested'"
    ).fetchall()
    topics = []
    for (t,) in rows:
        for topic in t.split(","):
            topic = topic.strip()
            if topic and topic not in topics:
                topics.append(topic)
    return topics[:10]


def _get_recent_read_titles(db, limit: int = 10) -> list[str]:
    rows = db.execute(
        "SELECT a.title FROM read_records r JOIN articles a ON r.article_id = a.id "
        "ORDER BY r.opened_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [r[0] for r in rows]
```

Then update the `analyze` endpoint to use the dispatch map:

```python
@router.get("/api/analyze/{article_id}")
@limiter.limit("10/minute")
async def analyze(article_id: str, type: str = Query(...), request: Request = None):
    db = get_db()
    ai = get_ai()
    if db is None or ai is None:
        return StreamingResponse(iter(["AI 服务未配置"]), media_type="text/event-stream")

    article = get_article(db, article_id)
    if article is None:
        return StreamingResponse(iter(["文章不存在"]), media_type="text/event-stream")

    full_text = article.get("full_text") or article.get("content") or ""
    if not full_text or full_text.startswith("["):
        full_text = await extract_full_text(article["url"])
        set_full_text(db, article_id, full_text)

    cached = get_cached_analysis(db, article_id, type)
    if cached:
        async def cached_stream():
            yield f"data: {json.dumps({'chunk': cached})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    prompts = _get_analyzer(ai, db, article_id, type, full_text)
    if prompts is None:
        return StreamingResponse(iter(["未知分析类型"]), media_type="text/event-stream")

    system, user = prompts
    max_tokens = 2048 if type == "what_it_means" else 1024
    return StreamingResponse(
        _sse_stream(ai, system, user, max_tokens, db, article_id, type),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: Write tests**

`tests/test_cross_cache.py`:
```python
import json


def test_cross_analysis_cache_table(db_conn):
    cols = db_conn.execute("PRAGMA table_info(cross_analysis_cache)").fetchall()
    col_names = [c[1] for c in cols]
    assert "cluster_id" in col_names
    assert "analysis_type" in col_names
    assert "article_ids" in col_names
    assert "content" in col_names


def test_cache_cross_analysis_write_read(db_conn):
    from db.models import cache_cross_analysis, get_cached_cross_analysis
    cache_cross_analysis(db_conn, "test-cluster-1", "cross_comparison",
                         "对比分析内容", ["art1", "art2", "art3"])
    result = get_cached_cross_analysis(db_conn, "test-cluster-1", "cross_comparison")
    assert result == "对比分析内容"


def test_cache_cross_analysis_upsert(db_conn):
    from db.models import cache_cross_analysis, get_cached_cross_analysis
    cache_cross_analysis(db_conn, "test-cluster-2", "cross_comparison", "第一版", ["a1"])
    cache_cross_analysis(db_conn, "test-cluster-2", "cross_comparison", "更新版", ["a1"])
    result = get_cached_cross_analysis(db_conn, "test-cluster-2", "cross_comparison")
    assert result == "更新版"


def test_get_user_topics_empty(db_conn):
    from web.routes.api import _get_user_topics
    topics = _get_user_topics(db_conn)
    assert topics == []


def test_get_recent_read_titles_empty(db_conn):
    from web.routes.api import _get_recent_read_titles
    titles = _get_recent_read_titles(db_conn)
    assert titles == []
```

- [ ] **Step 5: Run tests**
```
.venv\Scripts\python.exe -m pytest tests/test_cross_cache.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**
```bash
git add db/schema.py db/models.py web/routes/api.py tests/test_cross_cache.py
git commit -m "feat: cross_analysis_cache table + API dispatch map refactor"
```

---

### Task 2: "这意味着什么" 5 维升级（吸收反方观点）

**Files:**
- Modify: `D:\Projects\ai-news-digest\ai\analysis.py` — rewrite build_what_it_means_prompt
- Modify: `D:\Projects\ai-news-digest\web\routes\api.py` — update dispatch map
- Create: `D:\Projects\ai-news-digest\tests\test_analysis_v06.py`

- [ ] **Step 1: Rewrite build_what_it_means_prompt in ai/analysis.py**

Replace the existing `build_what_it_means_prompt` (lines 26-41) with:

```python
def build_what_it_means_prompt(full_text: str, concepts: list[str],
                                user_topics: list[str] | None = None,
                                read_titles: list[str] | None = None) -> tuple[str, str]:
    concepts_str = ", ".join(concepts) if concepts else "暂无记录"
    topics_str = ", ".join(user_topics) if user_topics else "暂无记录"
    read_str = "\n".join(f"- {t}" for t in (read_titles or [])[:10]) or "暂无记录"

    system = "你是一位 AI 领域的资深分析师。用户正在学习 AI，读了一篇文章后想全面理解它的含义。请用中文回答。"

    user = f"""用户已了解的概念：{concepts_str}
用户感兴趣的方向：{topics_str}
用户最近阅读的文章：
{read_str}

文章内容：
{full_text}

请从以下 5 个维度分析这篇文章（每段以维度标题开头）：

**1. 技术意义**
这项技术/产品/事件对AI技术栈和工程实践有什么实质影响？是渐进改进还是突破？

**2. 商业影响**
谁会受益？谁会受损？市场格局会发生什么变化？

**3. 行业趋势**
这是孤立事件还是更大趋势的信号？和最近的其他事件如何串联？

**4. 反方观点**
谁在反对或质疑这件事？反对的理由有多强？有什么局限性和风险没有被广泛讨论？

**5. 与你相关**
结合你最近读过的文章和感兴趣的方向，这篇文章对你意味着什么？是否填补了你之前的某个知识空白？

用通俗中文，避免术语堆砌。每段控制在3-5句。"""
    return system, user
```

- [ ] **Step 2: Write tests**

`tests/test_analysis_v06.py`:
```python
def test_what_it_means_prompt_5_dimensions():
    from ai.analysis import build_what_it_means_prompt
    system, user = build_what_it_means_prompt(
        "GPT-5 was released today with benchmark improvements.",
        ["transformer", "llm"],
        ["agent", "reasoning"],
        ["AI agents are the future", "Scaling laws debate"]
    )
    assert "技术意义" in user
    assert "商业影响" in user
    assert "行业趋势" in user
    assert "反方观点" in user
    assert "与你相关" in user
    assert "GPT-5" in user
    assert "agent" in user
    assert "Scaling laws debate" in user


def test_what_it_means_prompt_empty_context():
    from ai.analysis import build_what_it_means_prompt
    system, user = build_what_it_means_prompt("Some article text.", [])
    assert "技术意义" in user
    assert "暂无记录" in user  # empty concepts
```

- [ ] **Step 3: Run tests**
```
.venv\Scripts\python.exe -m pytest tests/test_analysis_v06.py -v
```
Expected: all PASS

- [ ] **Step 4: Commit**
```bash
git add ai/analysis.py tests/test_analysis_v06.py
git commit -m "feat: 5-dimension what_it_means prompt - tech/business/trend/counter/relevance"
```

---

### Task 3: 横向对比分析（轻量版）

**Files:**
- Modify: `D:\Projects\ai-news-digest\ai\analysis.py` — add build_cross_comparison_prompt
- Modify: `D:\Projects\ai-news-digest\web\routes\api.py` — add /api/cross-compare endpoint
- Modify: `D:\Projects\ai-news-digest\web\routes\reader.py` — pass cluster info to template
- Create: `D:\Projects\ai-news-digest\tests\test_cross_compare.py`

- [ ] **Step 1: Add build_cross_comparison_prompt to ai/analysis.py**

```python
def build_cross_comparison_prompt(cluster_articles: list[dict]) -> tuple[str, str]:
    """Generate cross-article comparison for articles in the same cluster.
    Only uses titles + source + cached core_insight (no what_it_means dependency).
    """
    articles_text = ""
    for i, art in enumerate(cluster_articles, 1):
        insight = art.get("insight", "") or "暂无观点"
        articles_text += (
            f"[{i}] {art.get('title', '')}\n"
            f"    来源: {art.get('source_id', '')}\n"
            f"    核心观点: {insight[:200]}\n\n"
        )

    system = "你是一个信息对比分析助手。帮助用户理解同一话题下不同报道的异同。"
    user = f"""以下是关于同一话题的 {len(cluster_articles)} 篇文章：

{articles_text}

请从以下角度对比这些文章：
1. **观点异同** — 各家报道的观点一致还是冲突？主要分歧在哪？
2. **事实一致性** — 关键数据和事实是否一致？有没有某家的数据明显异常？
3. **信息源质量** — 哪家更可信？谁在说事实、谁在发表观点？
4. **推荐阅读顺序** — 如果只能读 2 篇，应该读哪两篇？为什么？

用中文回答，简洁直接。"""
    return system, user
```

- [ ] **Step 2: Add /api/cross-compare endpoint to web/routes/api.py**

```python
@router.post("/api/cross-compare/{cluster_id}")
@limiter.limit("5/minute")
async def cross_compare(cluster_id: str, request: Request = None):
    db = get_db()
    ai = get_ai()
    if db is None or ai is None:
        return JSONResponse({"status": "error", "message": "AI 服务未配置"})

    # Check cache
    cached = get_cached_cross_analysis(db, cluster_id, "cross_comparison")
    if cached:
        return JSONResponse({"status": "ok", "content": cached, "cached": True})

    # Get cluster articles with core_insight
    arts = db.execute(
        "SELECT a.id, a.title, a.source_id, a.url, "
        "COALESCE(ac.content, '') as insight "
        "FROM cluster_articles ca "
        "JOIN articles a ON ca.article_id = a.id "
        "LEFT JOIN analysis_cache ac ON a.id = ac.article_id AND ac.analysis_type = 'core_insight' "
        "WHERE ca.cluster_id = ?",
        (cluster_id,)
    ).fetchall()

    if len(arts) < 3:
        return JSONResponse({"status": "error", "message": "至少需要 3 篇文章才能对比"})

    cluster_articles = [
        {"title": r[1], "source_id": r[2], "url": r[3], "insight": r[4]}
        for r in arts
    ]

    system, user = build_cross_comparison_prompt(cluster_articles)
    content, tokens = ai.chat(system, user, max_tokens=1024)

    article_ids = [r[0] for r in arts]
    cache_cross_analysis(db, cluster_id, "cross_comparison", content, article_ids,
                         tokens_used=tokens)

    return JSONResponse({"status": "ok", "content": content, "cached": False,
                         "article_count": len(arts)})
```

Note: Add the import for `build_cross_comparison_prompt` and the cross-cache CRUD functions at the top of api.py if not already imported.

- [ ] **Step 3: Write tests**

`tests/test_cross_compare.py`:
```python
import pytest


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


def test_cross_compare_insufficient_articles(client, db_conn):
    # Create a cluster with only 2 articles
    db_conn.execute("INSERT OR IGNORE INTO clusters (id, label, digest_date) VALUES ('test-cl-small', 'test', '2026-06-09')")
    db_conn.commit()
    resp = client.post("/api/cross-compare/test-cl-small")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "3" in data["message"]


def test_cross_compare_cached_response(client, db_conn):
    from db.models import cache_cross_analysis
    db_conn.execute("INSERT OR IGNORE INTO clusters (id, label, digest_date) VALUES ('test-cl-cached', 'test', '2026-06-09')")
    cache_cross_analysis(db_conn, "test-cl-cached", "cross_comparison",
                         "预缓存的对比结果", ["a1", "a2", "a3"])
    db_conn.commit()
    resp = client.post("/api/cross-compare/test-cl-cached")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cached"] is True
    assert data["content"] == "预缓存的对比结果"
```

- [ ] **Step 4: Run tests**
```
.venv\Scripts\python.exe -m pytest tests/test_cross_compare.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**
```bash
git add ai/analysis.py web/routes/api.py tests/test_cross_compare.py
git commit -m "feat: cross-article comparison - lightweight, only uses core_insight, >=3 articles trigger"
```

---

### Task 4: 阅读页 UI — 折叠式分析 + 过载控制

**Files:**
- Modify: `D:\Projects\ai-news-digest\web\templates\reader.html` — collapsible sections, cross-compare button
- Modify: `D:\Projects\ai-news-digest\web\templates\home.html` — cluster article count badge
- Modify: `D:\Projects\ai-news-digest\web\routes\reader.py` — pass cluster info
- Modify: `D:\Projects\ai-news-digest\web\routes\home.py` — pass cluster article counts
- Create: `D:\Projects\ai-news-digest\tests\test_web_v06.py`

- [ ] **Step 1: Read current reader.html and home.html**

Read both files first to understand structure before making changes.

- [ ] **Step 2: Upgrade reader.html — collapsible analysis sections**

Replace the "这意味着什么" button section with:

```html
<div class="analysis-section" id="what-it-means">
    <h3 style="cursor: pointer;" onclick="toggleSection('wim-content')">
        🔬 这意味着什么？ <span style="font-size:0.8em;color:#888;">（点击展开）</span>
    </h3>
    <div id="wim-content" style="display: none;">
        <button hx-get="/api/analyze/{{ article.id }}?type=what_it_means"
                hx-target="#wim-result" hx-swap="innerHTML"
                hx-ext="sse" sse-connect="/api/analyze/{{ article.id }}?type=what_it_means"
                class="btn btn-primary" onclick="this.style.display='none'">
            开始分析
        </button>
        <div id="wim-result"></div>
    </div>
</div>

{% if cluster_article_count >= 3 %}
<div class="analysis-section" id="cross-compare">
    <button hx-post="/api/cross-compare/{{ cluster_id }}"
            hx-target="#cross-compare-result" hx-swap="innerHTML"
            class="btn">
        ⚖️ 对比同话题 {{ cluster_article_count }} 篇文章
    </button>
    <div id="cross-compare-result" style="margin-top:12px;"></div>
</div>
{% endif %}

<script>
function toggleSection(id) {
    const el = document.getElementById(id);
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
}
</script>
```

- [ ] **Step 3: Update reader.py route to pass cluster info**

In `web/routes/reader.py`, update to query cluster article count:

```python
# After getting the article, query its cluster info
cluster_row = db.execute(
    "SELECT ca.cluster_id, (SELECT COUNT(*) FROM cluster_articles WHERE cluster_id = ca.cluster_id) "
    "FROM cluster_articles ca WHERE ca.article_id = ? LIMIT 1",
    (article_id,)
).fetchone()

cluster_id = cluster_row[0] if cluster_row else ""
cluster_count = cluster_row[1] if cluster_row else 0
```

Pass `cluster_id` and `cluster_article_count` to template context.

- [ ] **Step 4: Add cluster article count badge to home.html**

In the article list loop, add after article title:
```html
{% if article.get('cluster_count', 0) >= 3 %}
<span style="background: #9c27b0; color: white; font-size: 0.7em; padding: 2px 6px; border-radius: 3px;">
    +{{ article.cluster_count - 1 }}篇同类
</span>
{% endif %}
```

- [ ] **Step 5: Write tests**

`tests/test_web_v06.py`:
```python
def test_reader_page_has_collapsible_section(client, db_conn):
    # Insert test data
    db_conn.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("v06-test-1", "hackernews", "https://example.com/v06", "Test V06 Article")
    )
    db_conn.execute(
        "INSERT OR IGNORE INTO clusters (id, label, digest_date) VALUES (?, ?, ?)",
        ("v06-cluster", "Test Cluster", "2026-06-09")
    )
    db_conn.execute(
        "INSERT OR IGNORE INTO cluster_articles (cluster_id, article_id) VALUES (?, ?)",
        ("v06-cluster", "v06-test-1")
    )
    db_conn.commit()
    resp = client.get("/reader/v06-test-1")
    assert resp.status_code == 200
    assert "这意味着什么" in resp.text


def test_reader_no_cross_compare_when_few_articles(client, db_conn):
    db_conn.execute(
        "INSERT OR IGNORE INTO articles (id, source_id, url, title) VALUES (?, ?, ?, ?)",
        ("v06-solo", "hackernews", "https://example.com/solo", "Solo Article")
    )
    db_conn.execute(
        "INSERT OR IGNORE INTO clusters (id, label, digest_date) VALUES (?, ?, ?)",
        ("v06-cluster-solo", "Solo Cluster", "2026-06-09")
    )
    db_conn.execute(
        "INSERT OR IGNORE INTO cluster_articles (cluster_id, article_id) VALUES (?, ?)",
        ("v06-cluster-solo", "v06-solo")
    )
    db_conn.commit()
    resp = client.get("/reader/v06-solo")
    # With only 1 article in cluster, cross-compare should NOT appear
    assert "对比同话题" not in resp.text


def test_home_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
```

- [ ] **Step 6: Run tests**
```
.venv\Scripts\python.exe -m pytest tests/test_web_v06.py -v
```
Expected: all PASS

- [ ] **Step 7: Commit**
```bash
git add web/templates/reader.html web/templates/home.html web/routes/reader.py web/routes/home.py tests/test_web_v06.py
git commit -m "feat: collapsible analysis UI - 5D what_it_means accordion, cross-compare button, cluster badge"
```

---

### Task 5: 集成验证 + 全量回归

**Files:**
- No new files — integration verification

- [ ] **Step 1: Run full test suite**
```
.venv\Scripts\python.exe -m pytest tests/ -v --cov --cov-report=term
```
Expected: 166+ tests pass, coverage >= 82% (no regression from v0.5)

- [ ] **Step 2: Verify specific v0.6 behaviors**
- [ ] 5-dimension prompt generates all 5 sections
- [ ] cross_analysis_cache table works with UNIQUE constraint
- [ ] /api/cross-compare rejects clusters with <3 articles
- [ ] /api/cross-compare returns cached result on second call
- [ ] reader.html shows cross-compare button only when cluster >=3
- [ ] reader.html what_it_means section is collapsible

- [ ] **Step 3: Commit**
```bash
git add tests/
git commit -m "test: v0.6 integration verification - 166+ tests, coverage >=82%"
```

---

## Final Integration

After all 5 tasks complete:
```
.venv\Scripts\python.exe -m pytest tests/ -v --cov --tb=short
```
Expected: 175+ tests pass, coverage >= 82%
