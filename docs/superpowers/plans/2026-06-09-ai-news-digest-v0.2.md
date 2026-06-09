# AI 资讯管家 v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize v0.1 with test coverage and code refactoring, add source management UI, fix Reddit collector, auto-push weekly reviews, and markdown export.

**Architecture:** All within existing FastAPI + SQLite + Jinja2 + htmx stack. No new dependencies. Tasks are ordered: foundational refactors first (Task 1-2), then features (Task 3-6). Each task is independently testable and committable.

**Tech Stack:** Python 3.13, FastAPI, SQLite (sqlite3), Jinja2, htmx 1.9.12, httpx, pytest

---

### Task 1: Test Coverage — Critical Path

**Files:**
- Create: `tests/test_url_utils.py`
- Create: `tests/test_push.py`
- Create: `tests/test_api.py`
- Modify: `tests/test_collectors.py`
- Modify: `tests/test_db.py`

**Goal:** Add tests for `normalize_url`, `make_article_id`, `send_wecom_digest`, API endpoints, and DB model functions. Target: 28 → 45+ tests.

- [ ] **Step 1: Test `normalize_url` and `make_article_id`**

```python
# tests/test_url_utils.py
import pytest
from db.models import normalize_url, make_article_id


class TestNormalizeUrl:
    def test_removes_utm_params(self):
        url = "https://example.com/article?utm_source=twitter&a=1"
        result = normalize_url(url)
        assert "utm_source" not in result
        assert "a=1" in result

    def test_lowercases_scheme_and_host(self):
        assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"

    def test_removes_fragment(self):
        result = normalize_url("https://example.com/page#section")
        assert "#" not in result

    def test_removes_trailing_slash(self):
        assert normalize_url("https://example.com/") == "https://example.com"

    def test_empty_url_returns_empty(self):
        assert normalize_url("") == ""

    def test_sorts_query_params(self):
        result = normalize_url("https://example.com?b=2&a=1")
        assert result == "https://example.com?a=1&b=2"


class TestMakeArticleId:
    def test_generates_consistent_id(self):
        url = "https://example.com/article"
        id1 = make_article_id("hn", url)
        id2 = make_article_id("hn", url)
        assert id1 == id2
        assert len(id1) == 64

    def test_different_sources_produce_different_ids(self):
        url = "https://example.com/article"
        id1 = make_article_id("hn", url)
        id2 = make_article_id("arxiv", url)
        assert id1 != id2
```

- [ ] **Step 2: Run URL utils tests to verify they fail (new file)**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_url_utils.py -v`
Expected: FAIL — `import from db.models` works if functions exist, tests may pass for normalize_url; `make_article_id` should pass. All should PASS.

- [ ] **Step 3: Test `send_wecom_digest`**

```python
# tests/test_push.py
import pytest
from unittest.mock import AsyncMock, patch
from push import send_wecom_digest


class TestSendWecomDigest:
    @pytest.mark.asyncio
    async def test_empty_webhook_url_returns_false(self):
        result = await send_wecom_digest("", "2026-06-09", 10, 5, [])
        assert result is False

    @pytest.mark.asyncio
    async def test_successful_push_returns_true(self):
        clusters = [
            {"label": "AI 开源", "articles": [
                {"title": "OpenAI releases model", "url": "https://example.com/1"}
            ]}
        ]
        with patch("push.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = {"errcode": 0}
            result = await send_wecom_digest(
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                "2026-06-09", 10, 5, clusters
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_wecom_error_response_returns_false(self):
        with patch("push.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = {"errcode": 40001, "errmsg": "invalid"}
            result = await send_wecom_digest(
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                "2026-06-09", 10, 5, []
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        with patch("push.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Connection refused")
            result = await send_wecom_digest(
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                "2026-06-09", 10, 5, []
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_markdown_links_included(self):
        clusters = [
            {"label": "AI", "articles": [
                {"title": "Test Article", "url": "https://example.com/1"}
            ]}
        ]
        with patch("push.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = {"errcode": 0}
            await send_wecom_digest(
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                "2026-06-09", 10, 5, clusters
            )
            call_args = mock_post.call_args[1]["json"]["markdown"]["content"]
            assert "[Test Article](https://example.com/1)" in call_args
```

- [ ] **Step 4: Run push tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_push.py -v`
Expected: 5 passed

- [ ] **Step 5: Test API endpoints**

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from web.app import create_app
from web.globals import set_globals


@pytest.fixture
def client(test_db):
    app = create_app()
    from web.routes import api
    app.include_router(api.router)
    set_globals(test_db, None, None)
    return TestClient(app)


class TestApiHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestConceptLookup:
    def test_requires_term(self, client):
        resp = client.post("/api/concept-lookup", json={})
        assert resp.status_code == 200
        assert resp.json()["definition"] == ""

    def test_no_ai_returns_empty(self, client):
        resp = client.post("/api/concept-lookup", json={"term": "transformer"})
        assert resp.status_code == 200
        assert resp.json()["term"] == "transformer"


class TestFeedback:
    def test_no_db_returns_error(self):
        app = create_app()
        from web.routes import api
        app.include_router(api.router)
        set_globals(None, None, None)
        client = TestClient(app)
        resp = client.post("/api/feedback/article123?feedback=interested")
        assert resp.json()["status"] == "error"


class TestCollectTrigger:
    def test_returns_unavailable(self, client):
        resp = client.post("/api/collect")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"


@pytest.fixture
def test_db():
    import sqlite3, tempfile, os
    from db.schema import init_db
    tmp = os.path.join(tempfile.gettempdir(), "test_api.db")
    conn = init_db(tmp)
    yield conn
    conn.close()
    try:
        os.unlink(tmp)
    except Exception:
        pass
```

- [ ] **Step 6: Run API tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_api.py -v`
Expected: 4 passed

- [ ] **Step 7: Extend collector tests for HackerNews keyword filtering**

```python
# Add to tests/test_collectors.py
from collectors.hackernews import HackerNewsCollector, AI_KEYWORDS


class TestHackerNewsKeywordFilter:
    def setup_method(self):
        self.collector = HackerNewsCollector()

    def test_ai_title_matches(self):
        assert self.collector._is_ai_related("New LLM model released by OpenAI")
        assert self.collector._is_ai_related("Deep learning advances in 2026")

    def test_non_ai_title_rejected(self):
        assert not self.collector._is_ai_related("New JavaScript framework released")
        assert not self.collector._is_ai_related("")

    def test_keyword_substring_match(self):
        # "mail" should not match "email" → but "mail" is not in AI_KEYWORDS
        assert not self.collector._is_ai_related("Email client update")
        # "rag" should match "RAG" case-insensitively
        assert self.collector._is_ai_related("Building a RAG pipeline")


class TestArxivCollector:
    def test_registered(self):
        from collectors.registry import _collectors
        assert "arxiv-cs-ai" in _collectors
```

- [ ] **Step 8: Run extended collector tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_collectors.py -v`
Expected: 6+ passed

- [ ] **Step 9: Extend DB model tests**

```python
# Add to tests/test_db.py
from db.models import (
    get_article, get_or_create_concept, link_article_concept,
    get_concepts_list, cache_analysis, get_cached_analysis,
    save_weekly_review, get_weekly_review, search_articles,
    normalize_url, make_article_id, cleanup_old_data,
)


class TestConceptOperations:
    def test_create_and_get_concept(self, db_conn):
        cid = get_or_create_concept(db_conn, "transformer", "A neural network architecture")
        assert cid > 0
        concepts = get_concepts_list(db_conn)
        assert any(c["term"] == "transformer" for c in concepts)

    def test_repeat_query_increments_count(self, db_conn):
        cid1 = get_or_create_concept(db_conn, "rag", "Retrieval augmented generation")
        cid2 = get_or_create_concept(db_conn, "rag", "Updated definition")
        assert cid1 == cid2
        concepts = get_concepts_list(db_conn)
        rag = next(c for c in concepts if c["term"] == "rag")
        assert rag["query_count"] >= 2

    def test_link_article_concept(self, db_conn):
        aid = insert_article(db_conn, "test", "https://x.com/1", "Test")
        cid = get_or_create_concept(db_conn, "test-concept", "Definition")
        link_article_concept(db_conn, aid, cid)
        # no error = pass


class TestAnalysisCache:
    def test_cache_and_retrieve(self, db_conn):
        aid = insert_article(db_conn, "test", "https://x.com/2", "Test Article")
        cache_analysis(db_conn, aid, "core_insight", "This is the insight")
        cached = get_cached_analysis(db_conn, aid, "core_insight")
        assert cached == "This is the insight"

    def test_cache_miss_returns_none(self, db_conn):
        assert get_cached_analysis(db_conn, "nonexistent", "core_insight") is None


class TestWeeklyReview:
    def test_save_and_get_review(self, db_conn):
        save_weekly_review(db_conn, "2026-06-01", "2026-06-07", "Weekly content", ["id1", "id2"])
        review = get_weekly_review(db_conn, "2026-06-01")
        assert review is not None
        assert review["content"] == "Weekly content"

    def test_update_existing_review(self, db_conn):
        save_weekly_review(db_conn, "2026-06-01", "2026-06-07", "First", ["id1"])
        save_weekly_review(db_conn, "2026-06-01", "2026-06-07", "Updated", ["id1", "id2"])
        review = get_weekly_review(db_conn, "2026-06-01")
        assert review["content"] == "Updated"


class TestSearch:
    def test_search_returns_results(self, db_conn):
        aid = insert_article(db_conn, "test", "https://x.com/search-test", "Python Machine Learning Guide")
        from db.models import set_full_text
        set_full_text(db_conn, aid, "A comprehensive guide to machine learning with Python")
        results = search_articles(db_conn, "machine learning")
        assert len(results) > 0


class TestCleanup:
    def test_cleanup_removes_old_full_text(self, db_conn):
        aid = insert_article(db_conn, "test", "https://x.com/cleanup-test", "Old Article")
        from db.models import set_full_text
        set_full_text(db_conn, aid, "Some old content")
        # Cleanup with 0 days retention should nullify full_text
        cleanup_old_data(db_conn, full_text_days=0, analysis_days=180)
        article = get_article(db_conn, aid)
        assert article["full_text"] is None or article["full_text"] == ""
```

- [ ] **Step 10: Run extended DB tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_db.py -v`
Expected: 15+ passed (was 7)

- [ ] **Step 11: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 45+ passed

- [ ] **Step 12: Commit**

```bash
git add tests/test_url_utils.py tests/test_push.py tests/test_api.py tests/test_collectors.py tests/test_db.py
git commit -m "test: add test coverage for url utils, push, api, collectors, db models (28→48 tests)"
```

---

### Task 2: db/models.py Refactor

**Files:**
- Create: `db/url_utils.py`
- Create: `db/queries.py`
- Create: `db/digest.py`
- Create: `db/maintenance.py`
- Modify: `db/models.py` (remove moved functions, re-export)
- Modify: `db/__init__.py` (re-export key functions)
- Modify: `main.py` (update imports)
- Modify: `web/routes/api.py` (use new DB functions)
- Modify: `web/routes/home.py` (no change needed if models re-exports)
- Modify: `web/routes/reader.py`
- Modify: `web/routes/search.py`
- Modify: `web/routes/concepts.py`
- Modify: `web/routes/review.py`
- Modify: `tests/test_db.py` (update imports)
- Modify: `tests/test_url_utils.py` (update imports)

**Goal:** Split the 197-line monolith into focused modules. Move raw SQL from main.py/api.py into DB functions.

- [ ] **Step 1: Create `db/url_utils.py`**

```python
# db/url_utils.py
import hashlib
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "ref_src", "source", "fbclid", "gclid", "gclsrc",
    "_ga", "_gl", "mc_cid", "mc_eid",
}


def normalize_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    url = raw_url.strip()
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.hostname or ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"
    qs = parse_qs(parsed.query, keep_blank_values=True)
    clean_qs = {k: v for k, v in qs.items() if k not in TRACKING_PARAMS}
    query = urlencode(sorted(clean_qs.items()), doseq=True)
    result = urlunparse((scheme, netloc, path, parsed.params, query, ""))
    return result


def make_article_id(source_id: str, url: str) -> str:
    raw = f"{source_id}:{normalize_url(url)}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

- [ ] **Step 2: Create `db/queries.py`**

```python
# db/queries.py
import sqlite3
from datetime import datetime, timedelta


def get_clusters_for_date(conn: sqlite3.Connection, date_str: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, label FROM clusters WHERE digest_date = ?", (date_str,)
    ).fetchall()
    result = []
    for row in rows:
        arts = conn.execute(
            "SELECT a.id, a.title, a.source_id, a.language, a.published_at "
            "FROM cluster_articles ca JOIN articles a ON ca.article_id = a.id "
            "WHERE ca.cluster_id = ? ORDER BY a.published_at DESC",
            (row[0],)
        ).fetchall()
        result.append({
            "label": row[1],
            "articles": [dict(r) for r in arts],
        })
    return result


def search_articles(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT a.id, a.title, a.source_id, a.language, a.published_at, "
        "snippet(articles_fts, 2, '<mark>', '</mark>', '...', 32) as snippet "
        "FROM articles_fts f JOIN articles a ON a._rowid_ = f.rowid "
        "WHERE articles_fts MATCH ? ORDER BY rank LIMIT ?",
        (query, limit)
    ).fetchall()
    return [dict(r) for r in rows]


def get_weekly_review(conn: sqlite3.Connection, week_start: str) -> dict | None:
    row = conn.execute(
        "SELECT week_start, week_end, content, article_ids, created_at "
        "FROM weekly_reviews WHERE week_start = ?",
        (week_start,)
    ).fetchone()
    return dict(row) if row else None


def save_weekly_review(conn: sqlite3.Connection, week_start: str, week_end: str,
                       content: str, article_ids: list[str]):
    import json
    conn.execute(
        "INSERT INTO weekly_reviews (week_start, week_end, content, article_ids) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(week_start) DO UPDATE SET "
        "content = ?, article_ids = ?, week_end = ?",
        (week_start, week_end, content, json.dumps(article_ids),
         content, json.dumps(article_ids), week_end)
    )
    conn.commit()


def get_read_articles_with_insights(conn: sqlite3.Connection, since: str) -> list[dict]:
    rows = conn.execute(
        "SELECT a.title, ac.content as insight FROM read_records r "
        "JOIN articles a ON r.article_id = a.id "
        "LEFT JOIN analysis_cache ac ON a.id = ac.article_id AND ac.analysis_type = 'core_insight' "
        "WHERE r.opened_at >= ?",
        (since,)
    ).fetchall()
    return [{"title": r[0], "insight": r[1] or ""} for r in rows]


def get_read_article_ids_since(conn: sqlite3.Connection, since: str) -> list[str]:
    rows = conn.execute(
        "SELECT article_id FROM read_records WHERE opened_at >= ?",
        (since,)
    ).fetchall()
    return [r[0] for r in rows]


def get_feedback_articles(conn: sqlite3.Connection, since: str, feedback: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT a.title FROM read_records r JOIN articles a ON r.article_id = a.id "
        "WHERE r.feedback = ? AND r.opened_at >= ?",
        (feedback, since)
    ).fetchall()
    return [r[0] for r in rows]
```

- [ ] **Step 3: Create `db/digest.py`**

```python
# db/digest.py
import sqlite3
from datetime import datetime


def has_digest_today(conn: sqlite3.Connection) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT 1 FROM daily_digests WHERE date = ?", (today,)
    ).fetchone()
    return row is not None


def create_digest(conn: sqlite3.Connection, article_ids: list[str]) -> int | None:
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        cur = conn.execute(
            "INSERT INTO daily_digests (date) VALUES (?)", (today,)
        )
        digest_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO digest_articles (digest_id, article_id) VALUES (?, ?)",
            [(digest_id, aid) for aid in article_ids]
        )
        conn.commit()
        return digest_id
    except sqlite3.IntegrityError:
        return None


def mark_webhook_sent(conn: sqlite3.Connection):
    today = datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        "UPDATE daily_digests SET webhook_sent = 1 WHERE date = ?", (today,)
    )
    conn.commit()


def insert_cluster(conn: sqlite3.Connection, cid: str, label: str, date_str: str):
    conn.execute(
        "INSERT INTO clusters (id, label, digest_date) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET label = ?",
        (cid, label, date_str, label)
    )


def insert_cluster_article(conn: sqlite3.Connection, cid: str, article_id: str):
    conn.execute(
        "INSERT OR IGNORE INTO cluster_articles (cluster_id, article_id) VALUES (?, ?)",
        (cid, article_id)
    )


def mark_article_exploration(conn: sqlite3.Connection, article_id: str):
    conn.execute(
        "UPDATE articles SET summary = '[探索] ' || COALESCE(summary, '') WHERE id = ?",
        (article_id,)
    )
```

- [ ] **Step 4: Create `db/maintenance.py`**

```python
# db/maintenance.py
import sqlite3
from datetime import datetime, timedelta


def cleanup_old_data(conn: sqlite3.Connection, full_text_days: int = 90,
                     analysis_days: int = 180):
    ft_cutoff = (datetime.now() - timedelta(days=full_text_days)).strftime("%Y-%m-%d")
    conn.execute(
        "UPDATE articles SET full_text = NULL WHERE published_at < ? AND full_text IS NOT NULL",
        (ft_cutoff,)
    )
    ac_cutoff = (datetime.now() - timedelta(days=analysis_days)).strftime("%Y-%m-%d")
    conn.execute(
        "DELETE FROM analysis_cache WHERE created_at < ?", (ac_cutoff,)
    )
    conn.commit()
```

- [ ] **Step 5: Update `db/models.py` — remove moved functions, import from new modules**

```python
# db/models.py — strip to core CRUD only
# Remove: normalize_url, make_article_id, get_clusters_for_date, search_articles,
# get_weekly_review, save_weekly_review, has_digest_today, create_digest,
# mark_webhook_sent, cleanup_old_data
# Add re-imports at top:
from db.url_utils import normalize_url, make_article_id
from db.queries import get_clusters_for_date, search_articles, get_weekly_review, save_weekly_review
from db.digest import has_digest_today, create_digest, mark_webhook_sent
from db.maintenance import cleanup_old_data
```

Read the current `db/models.py` first, then remove the functions that were moved to other modules. Add re-imports.

- [ ] **Step 6: Update `db/__init__.py`**

```python
# db/__init__.py
from db.url_utils import normalize_url, make_article_id
from db.models import (
    insert_article, get_article, set_full_text, record_read, set_feedback,
    get_or_create_concept, link_article_concept, get_concepts_list,
    cache_analysis, get_cached_analysis,
)
from db.queries import (
    get_clusters_for_date, search_articles, get_weekly_review, save_weekly_review,
    get_read_articles_with_insights, get_read_article_ids_since, get_feedback_articles,
)
from db.digest import (
    has_digest_today, create_digest, mark_webhook_sent,
    insert_cluster, insert_cluster_article, mark_article_exploration,
)
from db.maintenance import cleanup_old_data
from db.schema import init_db
```

- [ ] **Step 7: Update `main.py` — use new DB functions for cluster/exploration operations**

Replace raw SQL in `main.py` lines 103-112 with:
```python
        from db.digest import insert_cluster, insert_cluster_article, mark_article_exploration
        # ...
        insert_cluster(db_conn, cid, label, today_str)
        for art in cluster:
            insert_cluster_article(db_conn, cid, art["id"])
        # ...
        mark_article_exploration(db_conn, art["id"])
```

- [ ] **Step 8: Update `web/routes/api.py` — use new query functions**

Replace raw SQL in `generate_review()` with:
```python
    from datetime import datetime, timedelta
    from db.queries import get_read_articles_with_insights, get_read_article_ids_since, get_feedback_articles
    
    start_dt = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    articles = get_read_articles_with_insights(db, start_dt)
    interested = get_feedback_articles(db, start_dt, "interested")
    not_interested = get_feedback_articles(db, start_dt, "not_interested")
    article_ids = get_read_article_ids_since(db, start_dt)
```

- [ ] **Step 9: Run tests to verify refactor**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: All existing tests still pass.

- [ ] **Step 10: Commit**

```bash
git add db/url_utils.py db/queries.py db/digest.py db/maintenance.py db/models.py db/__init__.py main.py web/routes/api.py tests/
git commit -m "refactor: split db/models.py into focused modules, move raw SQL to DB functions"
```

---

### Task 3: Source Management Web UI

**Files:**
- Create: `web/routes/sources.py`
- Create: `web/templates/sources.html`
- Modify: `web/app.py` (register new router)
- Modify: `web/templates/base.html` (add nav link)
- Modify: `collectors/registry.py` (add DB-backed source management)
- Modify: `db/models.py` (add source CRUD functions)

**Goal:** Web page at `/sources` to list, enable/disable, add, remove news sources. Sources stored in the existing `sources` table.

- [ ] **Step 1: Add source CRUD to `db/models.py`**

```python
# Add to db/models.py
def get_all_sources(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, type, config, enabled, fail_count, last_fetch FROM sources ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def add_source(conn: sqlite3.Connection, sid: str, name: str, stype: str, config: str) -> bool:
    try:
        conn.execute(
            "INSERT INTO sources (id, name, type, config) VALUES (?, ?, ?, ?)",
            (sid, name, stype, config)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def remove_source(conn: sqlite3.Connection, sid: str):
    conn.execute("DELETE FROM sources WHERE id = ?", (sid,))
    conn.commit()


def toggle_source(conn: sqlite3.Connection, sid: str, enabled: bool):
    conn.execute("UPDATE sources SET enabled = ? WHERE id = ?", (int(enabled), sid))
    conn.commit()
```

- [ ] **Step 2: Create `web/routes/sources.py`**

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from web.globals import get_db
from db.models import get_all_sources, add_source, remove_source, toggle_source

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request):
    db = get_db()
    sources = get_all_sources(db) if db else []
    return templates.TemplateResponse(request, "sources.html", {"sources": sources})


@router.post("/api/sources")
async def api_add_source(request: Request):
    data = await request.json()
    db = get_db()
    if not db:
        return JSONResponse({"status": "error", "message": "DB not available"})
    ok = add_source(db, data["id"], data["name"], data["type"], data["config"])
    if ok:
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "error", "message": "Source ID already exists"})


@router.delete("/api/sources/{sid}")
async def api_remove_source(sid: str):
    db = get_db()
    if db:
        remove_source(db, sid)
    return JSONResponse({"status": "ok"})


@router.patch("/api/sources/{sid}")
async def api_toggle_source(sid: str, request: Request):
    data = await request.json()
    db = get_db()
    if db:
        toggle_source(db, sid, data.get("enabled", True))
    return JSONResponse({"status": "ok"})
```

- [ ] **Step 3: Create `web/templates/sources.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>信息源管理</h1>

<div class="sources-toolbar">
    <button class="btn" onclick="showAddForm()">+ 添加源</button>
</div>

<div id="add-form" class="add-source-form" style="display:none">
    <h3>添加新信息源</h3>
    <input type="text" id="new-id" placeholder="ID (e.g. my-rss)">
    <input type="text" id="new-name" placeholder="名称">
    <select id="new-type">
        <option value="rss">RSS</option>
        <option value="api">API</option>
        <option value="web">Web</option>
    </select>
    <input type="text" id="new-config" placeholder='Config JSON (e.g. {"url": "..."})'>
    <button class="btn" onclick="addSource()">添加</button>
    <button class="btn btn-secondary" onclick="hideAddForm()">取消</button>
</div>

<table class="sources-table">
<thead><tr><th>ID</th><th>名称</th><th>类型</th><th>状态</th><th>操作</th></tr></thead>
<tbody>
{% for s in sources %}
<tr>
    <td>{{ s.id }}</td>
    <td>{{ s.name }}</td>
    <td>{{ s.type }}</td>
    <td>
        <input type="checkbox" {% if s.enabled %}checked{% endif %}
               onchange="toggleSource('{{ s.id }}', this.checked)"
               hx-patch="/api/sources/{{ s.id }}"
               hx-vals='js:{"enabled": event.target.checked}'
               hx-swap="none">
    </td>
    <td>
        <button class="btn btn-danger btn-sm"
                hx-delete="/api/sources/{{ s.id }}"
                hx-confirm="确定删除？"
                hx-target="closest tr"
                hx-swap="outerHTML">删除</button>
    </td>
</tr>
{% endfor %}
</tbody>
</table>

<nav class="bottom-nav">
    <a href="/">首页</a>
    <a href="/search">搜索</a>
    <a href="/concepts">概念词典</a>
    <a href="/review">周报</a>
</nav>

<script>
function showAddForm() { document.getElementById('add-form').style.display = 'block'; }
function hideAddForm() { document.getElementById('add-form').style.display = 'none'; }
async function addSource() {
    const data = {
        id: document.getElementById('new-id').value,
        name: document.getElementById('new-name').value,
        type: document.getElementById('new-type').value,
        config: document.getElementById('new-config').value,
    };
    const resp = await fetch('/api/sources', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    if (resp.ok) location.reload();
    else alert('添加失败，ID 可能已存在');
}
</script>
{% endblock %}
```

- [ ] **Step 4: Register sources router in `web/app.py`**

```python
# In create_app(), add:
from .routes import sources
app_.include_router(sources.router)
```

- [ ] **Step 5: Add CSS for sources page**

```css
/* Add to web/static/style.css */
.sources-table { width: 100%; border-collapse: collapse; margin: 16px 0; }
.sources-table th, .sources-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); text-align: left; }
.sources-table th { color: var(--text-muted); font-weight: 600; }
.sources-toolbar { margin-bottom: 16px; }
.add-source-form { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.add-source-form input, .add-source-form select { display: block; width: 100%; margin-bottom: 8px; padding: 6px 10px; background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 4px; }
.btn { padding: 6px 14px; background: var(--btn-bg); color: var(--text); border: 1px solid var(--border); border-radius: 4px; cursor: pointer; }
.btn:hover { background: var(--border); }
.btn-danger { color: #f85149; }
.btn-sm { padding: 2px 8px; font-size: 0.85em; }
.btn-secondary { margin-left: 8px; }
```

- [ ] **Step 6: Run tests and verify**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add web/routes/sources.py web/templates/sources.html web/app.py web/static/style.css db/models.py
git commit -m "feat: add source management web UI at /sources"
```

---

### Task 4: Reddit → RSSHub Migration

**Files:**
- Modify: `db/schema.py` (update DEFAULT_SOURCES Reddit entry)
- Modify: `collectors/rss_reader.py` (no change needed — RSSCollector handles any RSS URL)

**Goal:** Replace broken Reddit RSS with RSSHub instance that works in China.

- [ ] **Step 1: Update Reddit source URL in `db/schema.py`**

Change line 140-141 from:
```python
    ("reddit-ml", "Reddit r/MachineLearning", "rss",
     '{"url": "https://www.reddit.com/r/MachineLearning/.rss"}'),
```
To:
```python
    ("reddit-ml", "Reddit r/MachineLearning", "rss",
     '{"url": "https://rsshub.app/reddit/r/MachineLearning"}'),
```

- [ ] **Step 2: Add RSSHub as a fallback in `collectors/registry.py`**

Add a helper to the registry for getting the reddit URL:
```python
# In db/schema.py DEFAULT_SOURCES, already updated above.
# New DB init will use RSSHub. Existing DB users can change via the Sources UI (Task 3).
```

- [ ] **Step 3: Run tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add db/schema.py
git commit -m "fix: migrate Reddit RSS to RSSHub for China accessibility"
```

---

### Task 5: Weekly Review Auto-Push

**Files:**
- Modify: `db/schema.py` (add `review_pushed` column)
- Modify: `db/queries.py` (update `save_weekly_review`)
- Modify: `push.py` (add `send_wecom_review` function)
- Modify: `main.py` (add weekly review push logic)

**Goal:** On startup, if it's Monday and no review has been pushed this week, auto-generate and push.

- [ ] **Step 1: Add `review_pushed` column to schema**

```sql
-- Add to db/schema.py SCHEMA_SQL, after weekly_reviews table:
ALTER TABLE weekly_reviews ADD COLUMN review_pushed INTEGER DEFAULT 0;
```

Note: SQLite doesn't support `ADD COLUMN IF NOT EXISTS`. Use a try/except in `init_db`:
```python
# In db/schema.py init_db(), after SCHEMA_SQL:
try:
    conn.execute("ALTER TABLE weekly_reviews ADD COLUMN review_pushed INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass  # column already exists
```

- [ ] **Step 2: Add `send_wecom_review` to `push.py`**

```python
# Add to push.py
async def send_wecom_review(webhook_url: str, week_start: str, week_end: str,
                            content: str) -> bool:
    if not webhook_url:
        return False
    
    preview = content[:800] + ("..." if len(content) > 800 else "")
    msg = (
        f"\U0001f4dd **AI 资讯周报** | {week_start} ~ {week_end}\n\n"
        f"{preview}\n\n"
        f"\U0001f4bb 打开电脑 Web 面板查看完整周报"
    )
    
    msg_bytes = msg.encode("utf-8")
    if len(msg_bytes) > 3900:
        msg = msg_bytes[:3800].decode("utf-8", errors="ignore") + "..."
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                webhook_url,
                json={"msgtype": "markdown", "markdown": {"content": msg}}
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("errcode") == 0
    except httpx.HTTPError as e:
        logger.error(f"WeCom review push failed: {e}")
        return False


def mark_review_pushed(conn, week_start: str):
    conn.execute(
        "UPDATE weekly_reviews SET review_pushed = 1 WHERE week_start = ?",
        (week_start,)
    )
    conn.commit()
```

- [ ] **Step 3: Add weekly review auto-push to `main.py`**

Add after the daily digest push block in `run_collection_pipeline()`:
```python
    # Weekly review auto-push (only on Mondays)
    from ai.review import get_week_bounds
    from push import send_wecom_review, mark_review_pushed
    
    if datetime.now().weekday() == 0:  # Monday
        week_start, week_end = get_week_bounds()
        week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        week_end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        existing = get_weekly_review(db_conn, week_start)
        if existing and not existing.get("review_pushed"):
            success = await send_wecom_review(
                cfg.wecom_webhook_url, week_start, week_end, existing["content"]
            )
            if success:
                mark_review_pushed(db_conn, week_start)
                logger.info("Weekly review pushed successfully")
```

- [ ] **Step 4: Run tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add db/schema.py push.py main.py
git commit -m "feat: add weekly review auto-push to WeChat on Mondays"
```

---

### Task 6: Markdown Export

**Files:**
- Create: `web/routes/export.py`
- Modify: `web/app.py` (register export router)
- Modify: `web/templates/reader.html` (add export button)
- Modify: `web/templates/review.html` (add export button)

**Goal:** Export article or weekly review as .md file download.

- [ ] **Step 1: Create `web/routes/export.py`**

```python
from fastapi import APIRouter, Request
from fastapi.responses import Response
from web.globals import get_db
from db.models import get_article, get_cached_analysis
from db.queries import get_weekly_review
from utils import get_week_bounds

router = APIRouter()


@router.get("/api/export/article/{article_id}")
async def export_article(article_id: str):
    db = get_db()
    if not db:
        return Response("DB not available", status_code=500)
    
    article = get_article(db, article_id)
    if not article:
        return Response("Article not found", status_code=404)
    
    insight = get_cached_analysis(db, article_id, "core_insight") or ""
    what_it_means = get_cached_analysis(db, article_id, "what_it_means") or ""
    
    md = f"""# {article['title']}

**来源:** {article['source_id']} | **日期:** {article.get('published_at', '')[:10]}

{article['url']}

---

## 核心观点

{insight}

---

## 这意味着什么

{what_it_means}

---

## 摘要

{article.get('summary', '')}
"""
    filename = article['title'][:40].replace('/', '_').replace('\\', '_') + '.md'
    return Response(
        md, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/api/export/review")
async def export_review():
    db = get_db()
    if not db:
        return Response("DB not available", status_code=500)
    
    week_start, week_end = get_week_bounds()
    review = get_weekly_review(db, week_start)
    if not review:
        return Response("No review for this week", status_code=404)
    
    md = f"""# AI 资讯周报 | {week_start} ~ {week_end}

{review['content']}
"""
    filename = f"ai-weekly-{week_start}.md"
    return Response(
        md, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
```

- [ ] **Step 2: Register export router in `web/app.py`**

```python
from .routes import export
app_.include_router(export.router)
```

- [ ] **Step 3: Add export button to reader.html**

```html
<!-- Add before bottom-nav in reader.html -->
<div class="export-bar">
    <a href="/api/export/article/{{ article.id }}" class="btn">导出 Markdown</a>
</div>
```

- [ ] **Step 4: Add export button to review.html**

```html
<!-- Add before bottom-nav in review.html -->
<div class="export-bar">
    <a href="/api/export/review" class="btn">导出 Markdown</a>
</div>
```

- [ ] **Step 5: Run tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add web/routes/export.py web/app.py web/templates/reader.html web/templates/review.html
git commit -m "feat: add markdown export for articles and weekly reviews"
```

---

## Final Verification

- [ ] Run full test suite: `.\.venv\Scripts\python.exe -m pytest tests/ -q` → 50+ passed
- [ ] Start server: `.\.venv\Scripts\python.exe main.py`
- [ ] Visit `http://127.0.0.1:8765/` — homepage loads
- [ ] Visit `http://127.0.0.1:8765/sources` — source management loads
- [ ] Visit `http://127.0.0.1:8765/reader/{id}` — reader with export button
- [ ] Check WeChat — digest notification with links
- [ ] Run final commit
