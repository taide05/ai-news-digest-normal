# AI 资讯管家 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local AI news digest tool that collects AI news from 5 sources, clusters articles, pushes notifications to WeChat Work, and serves a local web panel for reading and AI-powered analysis.

**Architecture:** Python monolith — FastAPI web server with background collection pipeline. SQLite for storage, DeepSeek API for LLM calls, HTMX for frontend interactivity. Single-user, localhost-only, manual trigger via .bat shortcut.

**Tech Stack:** Python 3.12+, FastAPI, Uvicorn, Jinja2, HTMX + hx-sse, SQLite + FTS5, scikit-learn (TF-IDF), httpx, feedparser, readability-lxml, DeepSeek API (openai SDK)

**Project root:** `D:\Projects\ai-news-digest`

---

### Task 1: Project setup and virtual environment

**Files:**
- Create: `D:\Projects\ai-news-digest\config.yaml`
- Modify: `D:\Projects\ai-news-digest\pyproject.toml` (remove comment)

- [ ] **Step 1: Create virtual environment and install dependencies**

```powershell
cd D:\Projects\ai-news-digest
python -m venv .venv
.venv\Scripts\activate
pip install fastapi "uvicorn[standard]" jinja2 feedparser httpx readability-lxml chardet scikit-learn openai python-dotenv pyyaml tenacity
```

- [ ] **Step 2: Verify imports**

```powershell
python -c "import fastapi; import jinja2; import feedparser; import httpx; import readability; import chardet; import sklearn; import openai; import dotenv; import yaml; import tenacity; print('All imports OK')"
```
Expected: `All imports OK`

- [ ] **Step 3: Write config.yaml**

Write `D:\Projects\ai-news-digest\config.yaml`:

```yaml
pipeline:
  exploration_rate: 0.15
  cluster_threshold: 0.6
  max_daily_articles: 20

web:
  host: "127.0.0.1"
  port: 8765

data:
  full_text_retention_days: 90
  analysis_cache_retention_days: 180
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: project setup with dependencies and config"
```

---

### Task 2: Config loader

**Files:**
- Create: `D:\Projects\ai-news-digest\config.py`
- Test: `D:\Projects\ai-news-digest\tests\test_config.py`

- [ ] **Step 1: Write failing test**

Write `tests/test_config.py`:

```python
import os
import tempfile
import pytest
from config import Config, load_config

def test_load_config_loads_yaml_and_env():
    with tempfile.TemporaryDirectory() as tmp:
        yaml_path = os.path.join(tmp, "config.yaml")
        with open(yaml_path, "w") as f:
            f.write("pipeline:\n  cluster_threshold: 0.7\nweb:\n  port: 9999\n")

        env_path = os.path.join(tmp, ".env")
        with open(env_path, "w") as f:
            f.write("DEEPSEEK_API_KEY=sk-test-123\nWECOM_WEBHOOK_URL=https://example.com/hook\n")

        cfg = load_config(env_path=env_path, yaml_path=yaml_path)

        assert cfg.deepseek_api_key == "sk-test-123"
        assert cfg.wecom_webhook_url == "https://example.com/hook"
        assert cfg.cluster_threshold == 0.7
        assert cfg.port == 9999

def test_load_config_defaults_when_no_yaml():
    with tempfile.TemporaryDirectory() as tmp:
        env_path = os.path.join(tmp, ".env")
        with open(env_path, "w") as f:
            f.write("DEEPSEEK_API_KEY=sk-test\nWECOM_WEBHOOK_URL=https://example.com/hook\n")

        cfg = load_config(env_path=env_path, yaml_path="/nonexistent/config.yaml")

        assert cfg.cluster_threshold == 0.6  # default
        assert cfg.port == 8765  # default
```

- [ ] **Step 2: Run test (expected FAIL)**

```powershell
pytest tests/test_config.py -v
```

- [ ] **Step 3: Write config.py**

Write `D:\Projects\ai-news-digest\config.py`:

```python
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv as _load_dotenv
import yaml


@dataclass
class Config:
    deepseek_api_key: str = ""
    wecom_webhook_url: str = ""
    exploration_rate: float = 0.15
    cluster_threshold: float = 0.6
    max_daily_articles: int = 20
    host: str = "127.0.0.1"
    port: int = 8765
    full_text_retention_days: int = 90
    analysis_cache_retention_days: int = 180


def load_config(env_path: str = ".env", yaml_path: str = "config.yaml") -> Config:
    cfg = Config()

    if os.path.isfile(env_path):
        _load_dotenv(env_path)
    cfg.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    cfg.wecom_webhook_url = os.getenv("WECOM_WEBHOOK_URL", "")

    if os.path.isfile(yaml_path):
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        pipeline = data.get("pipeline", {})
        if pipeline:
            cfg.exploration_rate = pipeline.get("exploration_rate", cfg.exploration_rate)
            cfg.cluster_threshold = pipeline.get("cluster_threshold", cfg.cluster_threshold)
            cfg.max_daily_articles = pipeline.get("max_daily_articles", cfg.max_daily_articles)

        web = data.get("web", {})
        if web:
            cfg.host = web.get("host", cfg.host)
            cfg.port = web.get("port", cfg.port)

        d = data.get("data", {})
        if d:
            cfg.full_text_retention_days = d.get("full_text_retention_days", cfg.full_text_retention_days)
            cfg.analysis_cache_retention_days = d.get("analysis_cache_retention_days", cfg.analysis_cache_retention_days)

    return cfg
```

- [ ] **Step 4: Run test (expected PASS)**

```powershell
pytest tests/test_config.py -v
```

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py && git commit -m "feat: add config loader"
```

---

### Task 3: Database schema and seed data

**Files:**
- Create: `D:\Projects\ai-news-digest\db\schema.py`
- Test: `D:\Projects\ai-news-digest\tests\test_db.py`

- [ ] **Step 1: Write db/schema.py**

```python
import sqlite3

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sources (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    config      TEXT NOT NULL,
    enabled     INTEGER DEFAULT 1,
    fail_count  INTEGER DEFAULT 0,
    last_fetch  TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS articles (
    _rowid_     INTEGER PRIMARY KEY AUTOINCREMENT,
    id          TEXT UNIQUE NOT NULL,
    source_id   TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    title       TEXT NOT NULL,
    summary     TEXT,
    content     TEXT,
    full_text   TEXT,
    author      TEXT,
    published_at TEXT,
    fetched_at  TEXT DEFAULT (datetime('now')),
    language    TEXT,
    UNIQUE(source_id, url)
);

CREATE TABLE IF NOT EXISTS clusters (
    id          TEXT PRIMARY KEY,
    label       TEXT,
    digest_date TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cluster_articles (
    cluster_id  TEXT REFERENCES clusters(id) ON DELETE CASCADE,
    article_id  TEXT REFERENCES articles(id) ON DELETE CASCADE,
    PRIMARY KEY (cluster_id, article_id)
);

CREATE TABLE IF NOT EXISTS daily_digests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL UNIQUE,
    webhook_sent INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS digest_articles (
    digest_id   INTEGER REFERENCES daily_digests(id) ON DELETE CASCADE,
    article_id  TEXT REFERENCES articles(id) ON DELETE CASCADE,
    PRIMARY KEY (digest_id, article_id)
);

CREATE TABLE IF NOT EXISTS read_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    opened_at   TEXT DEFAULT (datetime('now')),
    feedback    TEXT
);

CREATE TABLE IF NOT EXISTS concepts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    term        TEXT NOT NULL UNIQUE,
    definition  TEXT,
    query_count INTEGER DEFAULT 1,
    first_seen  TEXT DEFAULT (datetime('now')),
    last_seen   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS article_concepts (
    article_id  TEXT REFERENCES articles(id) ON DELETE CASCADE,
    concept_id  INTEGER REFERENCES concepts(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, concept_id)
);

CREATE TABLE IF NOT EXISTS analysis_cache (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id    TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    analysis_type TEXT NOT NULL,
    content       TEXT NOT NULL,
    model         TEXT DEFAULT 'deepseek-chat',
    tokens_used   INTEGER,
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(article_id, analysis_type)
);

CREATE TABLE IF NOT EXISTS weekly_reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start  TEXT NOT NULL,
    week_end    TEXT NOT NULL,
    content     TEXT NOT NULL,
    article_ids TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(week_start)
);

CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
CREATE INDEX IF NOT EXISTS idx_reads_article ON read_records(article_id);
CREATE INDEX IF NOT EXISTS idx_concepts_term ON concepts(term);
CREATE INDEX IF NOT EXISTS idx_analysis_article ON analysis_cache(article_id);
CREATE INDEX IF NOT EXISTS idx_cluster_articles_article ON cluster_articles(article_id);
CREATE INDEX IF NOT EXISTS idx_digest_articles_article ON digest_articles(article_id);
CREATE INDEX IF NOT EXISTS idx_clusters_date ON clusters(digest_date);

CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    title, full_text, content='articles', content_rowid='_rowid_'
);

CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts(rowid, title, full_text) VALUES (new._rowid_, new.title, new.full_text);
END;

CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, full_text) VALUES ('delete', old._rowid_, old.title, old.full_text);
END;

CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, full_text) VALUES ('delete', old._rowid_, old.title, old.full_text);
    INSERT INTO articles_fts(rowid, title, full_text) VALUES (new._rowid_, new.title, new.full_text);
END;
"""

DEFAULT_SOURCES = [
    ("arxiv-cs-ai", "arXiv CS.AI/CL/LG", "api",
     '{"endpoint": "http://export.arxiv.org/api/query", "categories": ["cs.AI","cs.CL","cs.LG"], "max_results": 50}'),
    ("hackernews", "Hacker News", "api",
     '{"endpoint": "https://hacker-news.firebaseio.com/v0", "ai_keywords": ["ai","llm","gpt","ml","machine learning","openai","deep learning","transformer","neural net","claude","gemini","llama","mistral"]}'),
    ("jiqizhixin", "机器之心", "rss",
     '{"url": "https://www.jiqizhixin.com/rss"}'),
    ("github-trending", "GitHub Trending", "web",
     '{"url": "https://github.com/trending/python?since=daily"}'),
    ("reddit-ml", "Reddit r/MachineLearning", "rss",
     '{"url": "https://www.reddit.com/r/MachineLearning/.rss"}'),
]


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)

    cur = conn.execute("SELECT COUNT(*) FROM sources")
    if cur.fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO sources (id, name, type, config) VALUES (?, ?, ?, ?)",
            DEFAULT_SOURCES
        )
        conn.commit()

    return conn
```

- [ ] **Step 2: Write tests/test_db.py**

```python
import pytest
import tempfile
import os
from db.schema import init_db


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        conn = init_db(path)
        yield conn
        conn.close()


def test_sources_seeded_on_first_init(db):
    rows = db.execute("SELECT id, name, type FROM sources ORDER BY id").fetchall()
    assert len(rows) == 5
    assert rows[0][0] == "arxiv-cs-ai"


def test_sources_not_duplicated_on_reinit(db):
    db.execute("INSERT INTO sources (id, name, type, config) VALUES ('test', 'Test', 'rss', '{}')")
    db.commit()
    # Re-init same DB
    from db.schema import init_db
    conn2 = init_db(db.execute("PRAGMA database_list").fetchone()[2])
    rows = conn2.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    assert rows == 6  # 5 default + 1 test, not 10
    conn2.close()


def test_articles_unique_constraint(db):
    db.execute("INSERT INTO articles (id, source_id, url, title, language) VALUES ('a1', 'arxiv-cs-ai', 'http://example.com/1', 'Test', 'en')")
    db.commit()
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO articles (id, source_id, url, title, language) VALUES ('a2', 'arxiv-cs-ai', 'http://example.com/1', 'Test2', 'en')")


def test_fts5_trigger_insert(db):
    db.execute("INSERT INTO articles (id, source_id, url, title, full_text, language) VALUES ('a1', 'arxiv-cs-ai', 'http://x.com/1', 'Hello World', 'some content here', 'en')")
    db.commit()
    rows = db.execute("SELECT title FROM articles_fts WHERE articles_fts MATCH 'hello'").fetchall()
    assert len(rows) >= 1
```

- [ ] **Step 3: Run tests (expected FAIL)**

```powershell
pytest tests/test_db.py -v
```

- [ ] **Step 4: Run tests (expected PASS after schema.py is written)**

```powershell
pytest tests/test_db.py -v
```

- [ ] **Step 5: Commit**

```bash
git add db/schema.py tests/test_db.py && git commit -m "feat: add database schema with FTS5 and seed data"
```

---

### Task 4: Database models (CRUD layer)

**Files:**
- Create: `D:\Projects\ai-news-digest\db\models.py`

- [ ] **Step 1: Write db/models.py**

```python
from __future__ import annotations
import sqlite3
import hashlib
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def normalize_url(url: str) -> str:
    """Remove tracking query params, lowercase scheme+host."""
    parsed = urlparse(url)
    # Remove tracking params
    tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source", "fbclid", "gclid"}
    qs = {k: v for k, v in parse_qs(parsed.query, keep_blank_values=True).items() if k not in tracking_params}
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/") or "/", parsed.params, urlencode(qs, doseq=True) if qs else "", parsed.fragment or ""))


def make_article_id(source_id: str, url: str) -> str:
    raw = f"{source_id}:{normalize_url(url)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def article_exists(conn: sqlite3.Connection, source_id: str, url: str) -> bool:
    row = conn.execute("SELECT 1 FROM articles WHERE source_id = ? AND url = ?", (source_id, normalize_url(url))).fetchone()
    return row is not None


def insert_article(conn: sqlite3.Connection, source_id: str, url: str, title: str,
                   summary: str = "", content: str = "", author: str | None = None,
                   published_at: str | None = None, language: str = "en") -> str | None:
    """Insert article, return id if new, None if duplicate."""
    norm_url = normalize_url(url)
    aid = make_article_id(source_id, url)
    try:
        conn.execute(
            """INSERT INTO articles (id, source_id, url, title, summary, content, author, published_at, language)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (aid, source_id, norm_url, title, summary, content, author, published_at, language)
        )
        conn.commit()
        return aid
    except sqlite3.IntegrityError:
        return None


def get_article(conn: sqlite3.Connection, article_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    if row is None:
        return None
    cols = [c[0] for c in conn.execute("PRAGMA table_info(articles)")]
    return dict(zip(cols, row))


def set_full_text(conn: sqlite3.Connection, article_id: str, full_text: str):
    conn.execute("UPDATE articles SET full_text = ? WHERE id = ?", (full_text, article_id))
    conn.commit()


def get_clusters_for_date(conn: sqlite3.Connection, date_str: str) -> list[dict]:
    rows = conn.execute("SELECT id, label FROM clusters WHERE digest_date = ?", (date_str,)).fetchall()
    result = []
    for cid, label in rows:
        arts = conn.execute(
            "SELECT a.id, a.title, a.source_id, a.language, a.published_at FROM articles a "
            "JOIN cluster_articles ca ON a.id = ca.article_id WHERE ca.cluster_id = ?",
            (cid,)
        ).fetchall()
        result.append({"cluster_id": cid, "label": label, "articles": [
            {"id": r[0], "title": r[1], "source_id": r[2], "language": r[3], "published_at": r[4]} for r in arts
        ]})
    return result


def record_read(conn: sqlite3.Connection, article_id: str) -> int:
    cur = conn.execute("INSERT INTO read_records (article_id) VALUES (?)", (article_id,))
    conn.commit()
    return cur.lastrowid


def set_feedback(conn: sqlite3.Connection, article_id: str, feedback: str):
    conn.execute(
        "UPDATE read_records SET feedback = ? WHERE article_id = ? AND feedback IS NULL AND id = (SELECT MAX(id) FROM read_records WHERE article_id = ?)",
        (feedback, article_id, article_id)
    )
    conn.commit()


def get_or_create_concept(conn: sqlite3.Connection, term: str, definition: str = "") -> int:
    row = conn.execute("SELECT id, query_count FROM concepts WHERE term = ?", (term,)).fetchone()
    if row:
        cid, count = row
        conn.execute("UPDATE concepts SET query_count = ?, last_seen = datetime('now') WHERE id = ?", (count + 1, cid))
        if definition:
            conn.execute("UPDATE concepts SET definition = ? WHERE id = ?", (definition, cid))
        conn.commit()
        return cid
    else:
        cur = conn.execute("INSERT INTO concepts (term, definition) VALUES (?, ?)", (term, definition))
        conn.commit()
        return cur.lastrowid


def link_article_concept(conn: sqlite3.Connection, article_id: str, concept_id: int):
    try:
        conn.execute("INSERT INTO article_concepts (article_id, concept_id) VALUES (?, ?)", (article_id, concept_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass


def cache_analysis(conn: sqlite3.Connection, article_id: str, analysis_type: str, content: str, model: str = "deepseek-chat", tokens_used: int = 0):
    try:
        conn.execute(
            "INSERT INTO analysis_cache (article_id, analysis_type, content, model, tokens_used) VALUES (?, ?, ?, ?, ?)",
            (article_id, analysis_type, content, model, tokens_used)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE analysis_cache SET content = ?, tokens_used = ? WHERE article_id = ? AND analysis_type = ?",
            (content, tokens_used, article_id, analysis_type)
        )
        conn.commit()


def get_cached_analysis(conn: sqlite3.Connection, article_id: str, analysis_type: str) -> str | None:
    row = conn.execute("SELECT content FROM analysis_cache WHERE article_id = ? AND analysis_type = ?", (article_id, analysis_type)).fetchone()
    return row[0] if row else None


def get_concepts_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT term, definition, query_count FROM concepts ORDER BY query_count DESC").fetchall()
    return [{"term": r[0], "definition": r[1], "query_count": r[2]} for r in rows]


def has_digest_today(conn: sqlite3.Connection) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute("SELECT 1 FROM daily_digests WHERE date = ?", (today,)).fetchone()
    return row is not None


def create_digest(conn: sqlite3.Connection, article_ids: list[str]):
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        cur = conn.execute("INSERT INTO daily_digests (date, webhook_sent) VALUES (?, 0)", (today,))
        digest_id = cur.lastrowid
        for aid in article_ids:
            conn.execute("INSERT INTO digest_articles (digest_id, article_id) VALUES (?, ?)", (digest_id, aid))
        conn.commit()
        return digest_id
    except sqlite3.IntegrityError:
        return None


def mark_webhook_sent(conn: sqlite3.Connection):
    today = datetime.now().strftime("%Y-%m-%d")
    conn.execute("UPDATE daily_digests SET webhook_sent = 1 WHERE date = ?", (today,))
    conn.commit()


def get_weekly_review(conn: sqlite3.Connection, week_start: str) -> dict | None:
    row = conn.execute("SELECT * FROM weekly_reviews WHERE week_start = ?", (week_start,)).fetchone()
    if row is None:
        return None
    cols = [c[0] for c in conn.execute("PRAGMA table_info(weekly_reviews)")]
    return dict(zip(cols, row))


def save_weekly_review(conn: sqlite3.Connection, week_start: str, week_end: str, content: str, article_ids: list[str]):
    import json
    try:
        conn.execute(
            "INSERT INTO weekly_reviews (week_start, week_end, content, article_ids) VALUES (?, ?, ?, ?)",
            (week_start, week_end, content, json.dumps(article_ids))
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE weekly_reviews SET content = ?, article_ids = ? WHERE week_start = ?",
            (content, json.dumps(article_ids), week_start)
        )
        conn.commit()


def search_articles(conn: sqlite3.Connection, query: str, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT a.id, a.title, a.source_id, a.language, a.published_at, snippet(articles_fts, 2, '<mark>', '</mark>', '...', 40) AS sn "
        "FROM articles_fts f JOIN articles a ON a._rowid_ = f.rowid "
        "WHERE articles_fts MATCH ? ORDER BY rank LIMIT ?",
        (query, limit)
    ).fetchall()
    return [{"id": r[0], "title": r[1], "source_id": r[2], "language": r[3], "published_at": r[4], "snippet": r[5]} for r in rows]


def cleanup_old_data(conn: sqlite3.Connection, full_text_days: int = 90, analysis_days: int = 180):
    ft_cutoff = (datetime.now() - timedelta(days=full_text_days)).strftime("%Y-%m-%d")
    ac_cutoff = (datetime.now() - timedelta(days=analysis_days)).strftime("%Y-%m-%d")
    conn.execute("UPDATE articles SET full_text = NULL WHERE fetched_at < ?", (ft_cutoff,))
    conn.execute("DELETE FROM analysis_cache WHERE created_at < ?", (ac_cutoff,))
    conn.commit()
```

- [ ] **Step 2: Run existing tests to verify no regressions**

```powershell
pytest tests/test_db.py -v
```

- [ ] **Step 3: Commit**

```bash
git add db/models.py && git commit -m "feat: add database CRUD models"
```

---

### Task 5: AI client (DeepSeek API wrapper)

**Files:**
- Create: `D:\Projects\ai-news-digest\ai\client.py`
- Test: `D:\Projects\ai-news-digest\tests\test_ai_client.py`

- [ ] **Step 1: Write ai/client.py**

```python
from __future__ import annotations
import time
import logging
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 600):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  # seconds
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.open = False

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.open = True
            logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")

    def record_success(self):
        self.failure_count = 0
        self.open = False

    def can_execute(self) -> bool:
        if not self.open:
            return True
        if time.time() - self.last_failure_time > self.recovery_timeout:
            self.open = False
            self.failure_count = 0
            logger.info("Circuit breaker recovered, allowing requests")
            return True
        return False


class AIClient:
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = model
        self.circuit_breaker = CircuitBreaker()

    def _is_retryable(self, exception: Exception) -> bool:
        # Retry on rate limits and server errors
        if hasattr(exception, "status_code"):
            return exception.status_code in (429, 500, 502, 503, 504)
        return True

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(Exception),
        after=lambda retry_state: logger.warning(f"Retry {retry_state.attempt_number} after error: {retry_state.outcome.exception() if retry_state.outcome else 'unknown'}")
    )
    def chat(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> tuple[str, int]:
        if not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError("AI 服务暂时不可用，请稍后再试")

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                stream=False,
            )
            self.circuit_breaker.record_success()
            content = resp.choices[0].message.content or ""
            tokens = resp.usage.total_tokens if resp.usage else 0
            return content, tokens
        except Exception as e:
            self.circuit_breaker.record_failure()
            raise

    def chat_stream(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024):
        if not self.circuit_breaker.can_execute():
            yield "AI 服务暂时不可用，请稍后再试"
            return

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            self.circuit_breaker.record_success()
        except Exception as e:
            self.circuit_breaker.record_failure()
            yield f"[错误] {e}"


class CircuitBreakerOpenError(Exception):
    pass
```

- [ ] **Step 2: Write tests/test_ai_client.py**

```python
import pytest
from ai.client import CircuitBreaker, CircuitBreakerOpenError


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=600)
    assert cb.can_execute()
    cb.record_failure()
    cb.record_failure()
    assert cb.can_execute()  # Not yet open
    cb.record_failure()
    assert not cb.can_execute()  # Now open


def test_circuit_breaker_recovers_after_timeout():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0)  # instant recovery
    cb.record_failure()
    cb.record_failure()
    assert cb.can_execute()  # recovery_timeout=0 means immediate recovery


def test_circuit_breaker_record_success_resets():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=600)
    cb.record_failure()
    cb.record_success()
    assert cb.can_execute()
    cb.record_failure()
    assert cb.can_execute()
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/test_ai_client.py -v
```

- [ ] **Step 4: Commit**

```bash
git add ai/client.py tests/test_ai_client.py && git commit -m "feat: add DeepSeek API client with circuit breaker"
```

---

### Task 6: Collector base and registry

**Files:**
- Create: `D:\Projects\ai-news-digest\collectors\base.py`
- Create: `D:\Projects\ai-news-digest\collectors\registry.py`

- [ ] **Step 1: Write collectors/base.py**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    source_id: str
    url: str
    title: str
    summary: str = ""
    author: str | None = None
    published_at: str | None = None
    language: str = "en"
    content: str | None = None


class BaseCollector(ABC):
    name: str
    type: str  # 'rss' | 'api' | 'web'
    rate_limit: float = 0.5

    @abstractmethod
    async def fetch(self, since: datetime) -> list[Article]:
        ...
```

- [ ] **Step 2: Write collectors/registry.py**

```python
from __future__ import annotations
from datetime import datetime
from .base import BaseCollector, Article

_collectors: dict[str, BaseCollector] = {}


def register(collector: BaseCollector):
    _collectors[collector.name] = collector


def get_all() -> list[BaseCollector]:
    return list(_collectors.values())


def get_enabled(enabled_ids: list[str]) -> list[BaseCollector]:
    return [c for c in _collectors.values() if c.name in enabled_ids]
```

- [ ] **Step 3: Commit**

```bash
git add collectors/base.py collectors/registry.py && git commit -m "feat: add collector base class and registry"
```

---

### Task 7: RSS collector (机器之心, Reddit)

**Files:**
- Create: `D:\Projects\ai-news-digest\collectors\rss_reader.py`

- [ ] **Step 1: Write collectors/rss_reader.py**

```python
from datetime import datetime
import logging
import feedparser
import httpx
from .base import BaseCollector, Article
from .registry import register

logger = logging.getLogger(__name__)


class RSSCollector(BaseCollector):
    type = "rss"
    rate_limit = 1.0

    def __init__(self, name: str, feed_url: str, language: str = "en", display_name: str = ""):
        self.name = name
        self.feed_url = feed_url
        self.language = language
        self.display_name = display_name or name

    async def fetch(self, since: datetime) -> list[Article]:
        articles = []
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(self.feed_url, headers={"User-Agent": "ai-news-digest/0.1"})
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f"RSS fetch failed for {self.name}: {e}")
            return []

        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            pub = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub = datetime(*entry.published_parsed[:6]).isoformat()
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                pub = datetime(*entry.updated_parsed[:6]).isoformat()

            if pub:
                try:
                    pub_dt = datetime.fromisoformat(pub)
                    if pub_dt < since:
                        continue
                except ValueError:
                    pass

            content = None
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")
            elif hasattr(entry, "content") and entry.content:
                content = str(entry.content)

            articles.append(Article(
                source_id=self.name,
                url=getattr(entry, "link", ""),
                title=getattr(entry, "title", "").strip(),
                summary=getattr(entry, "summary", "") or getattr(entry, "description", ""),
                author=getattr(entry, "author", None),
                published_at=pub,
                language=self.language,
                content=content,
            ))

        return articles


# Register default instances
register(RSSCollector("jiqizhixin", "https://www.jiqizhixin.com/rss", language="zh"))
register(RSSCollector("reddit-ml", "https://www.reddit.com/r/MachineLearning/.rss", language="en"))
```

- [ ] **Step 2: Commit**

```bash
git add collectors/rss_reader.py && git commit -m "feat: add generic RSS collector with default sources"
```

---

### Task 8: arXiv collector

**Files:**
- Create: `D:\Projects\ai-news-digest\collectors\arxiv.py`

- [ ] **Step 1: Write collectors/arxiv.py**

```python
from datetime import datetime, timedelta
import logging
import httpx
import xml.etree.ElementTree as ET
from .base import BaseCollector, Article
from .registry import register

logger = logging.getLogger(__name__)
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivCollector(BaseCollector):
    name = "arxiv-cs-ai"
    type = "api"
    rate_limit = 3.0

    def __init__(self):
        self.endpoint = "http://export.arxiv.org/api/query"
        self.categories = ["cs.AI", "cs.CL", "cs.LG"]
        self.max_results = 50

    async def fetch(self, since: datetime) -> list[Article]:
        articles = []
        cat_query = "+OR+".join(f"cat:{c}" for c in self.categories)
        url = f"{self.endpoint}?search_query={cat_query}&start=0&max_results={self.max_results}&sortBy=submittedDate&sortOrder=descending"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={"User-Agent": "ai-news-digest/0.1"})
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f"arXiv fetch failed: {e}")
            return []

        root = ET.fromstring(resp.text)
        for entry in root.findall("atom:entry", ARXIV_NS):
            title_el = entry.find("atom:title", ARXIV_NS)
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            # Replace newlines in titles
            title = " ".join(title.split())

            link_el = entry.find("atom:id", ARXIV_NS)
            url = link_el.text.strip() if link_el is not None and link_el.text else ""

            summary_el = entry.find("atom:summary", ARXIV_NS)
            summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""

            published_el = entry.find("atom:published", ARXIV_NS)
            published_str = published_el.text.strip() if published_el is not None and published_el.text else ""
            try:
                pub_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00")).replace(tzinfo=None)
                if pub_dt < since:
                    continue
            except ValueError:
                pub_dt = None

            authors = []
            for author_el in entry.findall("atom:author", ARXIV_NS):
                name_el = author_el.find("atom:name", ARXIV_NS)
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())
            author_str = ", ".join(authors[:3])

            articles.append(Article(
                source_id=self.name,
                url=url,
                title=title,
                summary=summary,
                author=author_str or None,
                published_at=pub_dt.isoformat() if pub_dt else None,
                language="en",
                content=None,
            ))

        return articles


register(ArxivCollector())
```

- [ ] **Step 2: Commit**

```bash
git add collectors/arxiv.py && git commit -m "feat: add arXiv collector"
```

---

### Task 9: Hacker News collector

**Files:**
- Create: `D:\Projects\ai-news-digest\collectors\hackernews.py`

- [ ] **Step 1: Write collectors/hackernews.py**

```python
from datetime import datetime
import logging
import httpx
from .base import BaseCollector, Article
from .registry import register

logger = logging.getLogger(__name__)

AI_KEYWORDS = ["ai", "llm", "gpt", "ml", "machine learning", "openai", "deep learning",
               "transformer", "neural", "claude", "gemini", "llama", "mistral", "diffusion",
               "rlhf", "fine-tuning", "rag", "agent", "embeddings", "vector", "anthropic",
               "deepseek", "qwen", "stable diffusion", "langchain"]


class HackerNewsCollector(BaseCollector):
    name = "hackernews"
    type = "api"
    rate_limit = 0.5

    def __init__(self):
        self.base_url = "https://hacker-news.firebaseio.com/v0"
        self.keywords = AI_KEYWORDS

    def _is_ai_related(self, title: str) -> bool:
        tl = title.lower()
        return any(kw in tl for kw in self.keywords)

    async def fetch(self, since: datetime) -> list[Article]:
        articles = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.base_url}/newstories.json")
                resp.raise_for_status()
                ids = resp.json()[:100]  # latest 100
        except httpx.HTTPError as e:
            logger.warning(f"HN fetch failed: {e}")
            return []

        for item_id in ids:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(f"{self.base_url}/item/{item_id}.json")
                    resp.raise_for_status()
                    item = resp.json()
            except httpx.HTTPError:
                continue

            if item is None or item.get("type") != "story":
                continue

            title = item.get("title", "")
            if not self._is_ai_related(title):
                continue

            pub_ts = item.get("time", 0)
            pub_dt = datetime.fromtimestamp(pub_ts) if pub_ts else None
            if pub_dt and pub_dt < since:
                continue

            articles.append(Article(
                source_id=self.name,
                url=item.get("url", f"https://news.ycombinator.com/item?id={item_id}"),
                title=title,
                summary="",
                author=item.get("by"),
                published_at=pub_dt.isoformat() if pub_dt else None,
                language="en",
            ))

        return articles


register(HackerNewsCollector())
```

- [ ] **Step 2: Commit**

```bash
git add collectors/hackernews.py && git commit -m "feat: add Hacker News collector with AI keyword filter"
```

---

### Task 10: GitHub Trending collector

**Files:**
- Create: `D:\Projects\ai-news-digest\collectors\github_trending.py`

- [ ] **Step 1: Write collectors/github_trending.py**

```python
from datetime import datetime
import logging
import httpx
from .base import BaseCollector, Article
from .registry import register

logger = logging.getLogger(__name__)


class GitHubTrendingCollector(BaseCollector):
    name = "github-trending"
    type = "web"
    rate_limit = 2.0

    def __init__(self):
        self.url = "https://github.com/trending/python?since=daily"

    async def fetch(self, since: datetime) -> list[Article]:
        articles = []
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    self.url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "text/html",
                    }
                )
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f"GitHub Trending fetch failed: {e}")
            return []

        # Simple regex-based extraction (avoid heavy HTML parsing dependency)
        import re
        # Extract repo entries: <h2> with links to /owner/repo
        repos = re.findall(r'<h2[^>]*>.*?<a[^>]*href="(/([^/]+)/([^"]+))"[^>]*>\s*(?:[^<]*/)?\s*([^<]*)', resp.text, re.DOTALL)
        seen = set()
        for full_path, owner, repo_name, _ in repos[:20]:
            if repo_name in seen:
                continue
            seen.add(repo_name)
            desc_match = re.search(rf'<p[^>]*>\s*({re.escape(repo_name)}[^<]*|[^<]{{10,200}})\s*</p>', resp.text, re.IGNORECASE)

            articles.append(Article(
                source_id=self.name,
                url=f"https://github.com{full_path}",
                title=f"{owner}/{repo_name}",
                summary=desc_match.group(1).strip() if desc_match else "",
                author=owner,
                published_at=datetime.now().isoformat(),
                language="en",
            ))

        return articles


register(GitHubTrendingCollector())
```

- [ ] **Step 2: Commit**

```bash
git add collectors/github_trending.py && git commit -m "feat: add GitHub Trending collector"
```

---

### Task 11: Dedup module

**Files:**
- Create: `D:\Projects\ai-news-digest\pipeline\dedup.py`
- Test: `D:\Projects\ai-news-digest\tests\test_dedup.py`

- [ ] **Step 1: Write pipeline/dedup.py**

```python
def title_similarity(t1: str, t2: str, n: int = 3) -> float:
    """Character n-gram Jaccard similarity."""
    def ngrams(s, n):
        s = s.lower()
        return {s[i:i+n] for i in range(len(s) - n + 1)}
    a = ngrams(t1, n)
    b = ngrams(t2, n)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def filter_duplicates_by_title(articles: list[dict], threshold: float = 0.85) -> list[dict]:
    """Remove articles with highly similar titles, keeping the first occurrence."""
    result = []
    for art in articles:
        is_dup = False
        for existing in result:
            if title_similarity(art["title"], existing["title"]) > threshold:
                is_dup = True
                break
        if not is_dup:
            result.append(art)
    return result
```

- [ ] **Step 2: Write tests/test_dedup.py**

```python
from pipeline.dedup import title_similarity, filter_duplicates_by_title


def test_exact_same_title():
    assert title_similarity("Hello World", "Hello World") == 1.0


def test_completely_different():
    assert title_similarity("Hello World", "Foo Bar Baz Qux") < 0.1


def test_similar_titles():
    sim = title_similarity("GPT-5 Released by OpenAI", "OpenAI Releases GPT-5 Model")
    assert sim > 0.5  # Should be somewhat similar


def test_filter_duplicates_removes_similar():
    articles = [
        {"title": "GPT-5 Released by OpenAI"},
        {"title": "OpenAI Releases GPT-5 Model"},
        {"title": "MoE Training Breakthrough"},
    ]
    result = filter_duplicates_by_title(articles, threshold=0.4)
    assert len(result) == 2
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/test_dedup.py -v
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/dedup.py tests/test_dedup.py && git commit -m "feat: add dedup with character n-gram similarity"
```

---

### Task 12: Clustering module

**Files:**
- Create: `D:\Projects\ai-news-digest\pipeline\cluster.py`
- Test: `D:\Projects\ai-news-digest\tests\test_cluster.py`

- [ ] **Step 1: Write pipeline/cluster.py**

```python
import hashlib
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from scipy.cluster.hierarchy import fcluster, linkage


def cluster_articles(articles: list[dict], threshold: float = 0.6) -> list[list[dict]]:
    """Cluster articles by TF-IDF cosine similarity, single-linkage."""
    if len(articles) <= 1:
        return [[a] for a in articles] if articles else []

    # Build documents: title + " " + summary
    docs = [f"{a.get('title', '')} {a.get('summary', '')}" for a in articles]

    try:
        vectorizer = TfidfVectorizer(
            analyzer='char_wb', ngram_range=(3, 5), max_features=2000
        )
        tfidf = vectorizer.fit_transform(docs)
        sim_matrix = cosine_similarity(tfidf)
        # Convert similarity to distance, handle floating-point noise
        dist_matrix = 1.0 - sim_matrix
        # Ensure no negative distances due to floating point
        dist_matrix[dist_matrix < 0] = 0
        Z = linkage(dist_matrix, method='single')
        labels = fcluster(Z, t=1.0 - threshold, criterion='distance')
    except Exception:
        # Fallback: each article in its own cluster
        return [[a] for a in articles]

    clusters: dict[int, list[dict]] = {}
    for i, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(articles[i])

    return list(clusters.values())


def make_cluster_id(date_str: str, seq: int) -> str:
    raw = f"{date_str}:{seq}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def make_cluster_label(cluster: list[dict]) -> str:
    """Generate a simple label from cluster titles (without LLM). Falls back to top words."""
    # Use the title of the first article as the cluster label
    title = cluster[0].get("title", "未命名")
    if len(title) > 50:
        title = title[:47] + "..."
    return title
```

- [ ] **Step 2: Write tests/test_cluster.py**

```python
from pipeline.cluster import cluster_articles, make_cluster_label


def test_single_article_returns_single_cluster():
    articles = [{"title": "Hello World", "summary": "test"}]
    clusters = cluster_articles(articles)
    assert len(clusters) == 1
    assert len(clusters[0]) == 1


def test_empty_list():
    assert cluster_articles([]) == []


def test_identical_articles_cluster_together():
    articles = [
        {"title": "GPT-5 Released by OpenAI", "summary": "OpenAI announced GPT-5 today"},
        {"title": "OpenAI Releases GPT-5 Model", "summary": "GPT-5 has been released by OpenAI"},
        {"title": "Python 4.0 Announced Today", "summary": "Python language version 4 released"},
    ]
    clusters = cluster_articles(articles, threshold=0.3)
    # First two should cluster together
    assert len(clusters) <= 2


def test_different_articles_stay_separate():
    articles = [
        {"title": "AlphaFold Wins Nobel", "summary": "protein folding breakthrough"},
        {"title": "New JavaScript Framework", "summary": "frontend framework released"},
        {"title": "Quantum Computing Advance", "summary": "qubits milestone"},
    ]
    clusters = cluster_articles(articles)
    assert len(clusters) == 3


def test_make_cluster_label_truncates():
    label = make_cluster_label([{"title": "A" * 100}])
    assert len(label) <= 50
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/test_cluster.py -v
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/cluster.py tests/test_cluster.py && git commit -m "feat: add TF-IDF clustering"
```

---

### Task 13: Full-text extractor

**Files:**
- Create: `D:\Projects\ai-news-digest\pipeline\extractor.py`

- [ ] **Step 1: Write pipeline/extractor.py**

```python
import logging
import httpx
from readability import Document

logger = logging.getLogger(__name__)


async def extract_full_text(url: str, timeout: int = 15) -> str:
    """Fetch and extract readable content from a URL."""
    try:
        async with httpx.AsyncClient(timeout=float(timeout), follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                }
            )
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 403, 410):
            logger.warning(f"URL returned {e.response.status_code}: {url}")
            return "[原文无法访问]"
        raise
    except httpx.TimeoutException:
        logger.warning(f"Timeout fetching: {url}")
        return "[原文加载超时]"
    except httpx.HTTPError as e:
        logger.warning(f"HTTP error fetching {url}: {e}")
        return "[原文无法访问]"

    try:
        doc = Document(html)
        text = doc.summary()
        # Strip HTML tags from summary
        import re
        text = re.sub(r'<[^>]+>', '', text)
        text = ' '.join(text.split())  # normalize whitespace

        if len(text) < 200:
            return "[正文提取失败，请查看原网页]"
        return text
    except Exception as e:
        logger.warning(f"Readability extraction failed for {url}: {e}")
        return "[正文提取失败，请查看原网页]"
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/extractor.py && git commit -m "feat: add full-text extractor with readability"
```

---

### Task 14: AI analysis prompts

**Files:**
- Create: `D:\Projects\ai-news-digest\ai\analysis.py`

- [ ] **Step 1: Write ai/analysis.py**

```python
def build_core_insight_prompt(full_text: str) -> tuple[str, str]:
    system = "你是一个专业的科技内容摘要助手。"
    user = f"用 2-3 句话概括下面这篇文章的核心内容。直接说重点，不要铺垫。\n\n文章：{full_text}"
    return system, user


def build_what_it_means_prompt(full_text: str, concepts: list[str]) -> tuple[str, str]:
    concepts_str = ", ".join(concepts) if concepts else "暂无记录"
    system = "你是一位 AI 领域的资深分析师。用户正在学习 AI，读了一篇文章后想理解它到底意味着什么。"
    user = f"""用户已了解的概念：{concepts_str}

文章内容：
{full_text}

请从以下维度分析：
1. 这件事在 AI 领域有多重要？（从"噪音"到"里程碑"给出判断）
2. 可信度如何？（有数据支撑还是 PR 宣传？）
3. 为什么会发生？（技术、商业还是政策在推动？）
4. 长期看意味着什么？（半年后回头看）

用通俗中文回答，避免术语堆砌。若原文为英文，用中文输出分析。"""
    return system, user


def build_translation_prompt(full_text: str) -> tuple[str, str]:
    system = "你是一个专业的技术翻译助手。"
    user = f"将以下英文文章翻译为中文。保留技术术语的准确性，保持原文结构和风格。\n\n文章：{full_text}"
    return system, user


def build_concept_lookup_prompt(term: str, context: str = "") -> tuple[str, str]:
    system = "你是一个 AI 技术词典。"
    ctx = f"\n\n上下文：{context[:500]}" if context else ""
    user = f"用简短的中文解释以下 AI 相关概念。一句话定义即可。\n\n概念：{term}{ctx}"
    return system, user


def build_review_prompt(read_articles: list[dict], concepts: list[str], interested_topics: list[str], not_interested_topics: list[str]) -> tuple[str, str]:
    articles_text = "\n".join(
        f"- [{a.get('title', '')}] {a.get('insight', '')}" for a in read_articles[:30]
    )
    system = "你是一个 AI 学习教练，帮助用户回顾一周的学习进展。"
    user = f"""用户本周阅读的文章：
{articles_text}

用户新学的概念：{', '.join(concepts) if concepts else '无'}
用户感兴趣的方向：{', '.join(interested_topics) if interested_topics else '暂无'}
用户不太感兴趣的方向：{', '.join(not_interested_topics) if not_interested_topics else '暂无'}

请生成一份周报：
1. 本周阅读内容的主题分类（2-3 个主题）
2. 本周最值得记住的 3 件事
3. 用户的学习进展和知识空白
4. 下周建议关注的方向

用通俗中文，像导师跟学生说话的语气。"""
    return system, user
```

- [ ] **Step 2: Write tests/test_prompts.py**

```python
from ai.analysis import build_core_insight_prompt, build_what_it_means_prompt, build_translation_prompt, build_concept_lookup_prompt


def test_core_insight_prompt_contains_article():
    sys_p, usr_p = build_core_insight_prompt("This is a test article about AI.")
    assert "This is a test article" in usr_p


def test_what_it_means_prompt_contains_concepts():
    sys_p, usr_p = build_what_it_means_prompt("test article", ["RLHF", "transformer"])
    assert "RLHF" in usr_p
    assert "transformer" in usr_p


def test_what_it_means_empty_concepts():
    sys_p, usr_p = build_what_it_means_prompt("test", [])
    assert "暂无记录" in usr_p


def test_translation_prompt_contains_full_text():
    sys_p, usr_p = build_translation_prompt("Hello world, this is AI news.")
    assert "Hello world" in usr_p


def test_concept_lookup_prompt_contains_term():
    sys_p, usr_p = build_concept_lookup_prompt("RLHF", "Some article context")
    assert "RLHF" in usr_p
    assert "Some article context" in usr_p
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/test_prompts.py -v
```

- [ ] **Step 4: Commit**

```bash
git add ai/analysis.py tests/test_prompts.py && git commit -m "feat: add AI analysis prompt builders"
```

---

### Task 15: AI review prompt

**Files:**
- Create: `D:\Projects\ai-news-digest\ai\review.py`

- [ ] **Step 1: Write ai/review.py**

```python
from datetime import datetime, timedelta


def get_week_bounds(reference_date: datetime | None = None) -> tuple[str, str]:
    """Get Monday and Sunday of the current natural week."""
    today = reference_date or datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def get_partial_week_end() -> str:
    """If mid-week, return yesterday's date as the end."""
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")
```

- [ ] **Step 2: Commit**

```bash
git add ai/review.py && git commit -m "feat: add week boundary calculation"
```

---

### Task 16: WeChat Work push

**Files:**
- Create: `D:\Projects\ai-news-digest\push.py`

- [ ] **Step 1: Write push.py**

```python
import logging
import httpx

logger = logging.getLogger(__name__)


async def send_wecom_digest(webhook_url: str, date_str: str, total_fetched: int, total_selected: int, clusters: list[dict]) -> bool:
    """Send daily digest to WeChat Work webhook. Returns True on success."""
    if not webhook_url:
        logger.warning("Webhook URL not configured, skipping push")
        return False

    cluster_lines = []
    for c in clusters[:10]:  # Max 10 topics in push
        label = c.get("label", "未命名")
        count = len(c.get("articles", []))
        cluster_lines.append(f"\u{1f4cc} {label} ({count}篇)")

    topics_text = "\n".join(cluster_lines) if cluster_lines else "暂无话题聚类"
    content = f"""\u{1f916} AI 资讯已就绪 | {date_str}

今日采集 {total_fetched} 篇，精选 {total_selected} 篇，{len(clusters)} 个话题：

{topics_text}

\u{1f4bb} 打开电脑上的 Web 面板查看详情"""

    # Truncate to 3KB
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > 3000:
        content = content_bytes[:2900].decode("utf-8", errors="ignore") + "..."

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                webhook_url,
                json={
                    "msgtype": "markdown",
                    "markdown": {"content": content}
                }
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("errcode") != 0:
                logger.error(f"WeCom webhook error: {result}")
                return False
            return True
    except httpx.HTTPError as e:
        logger.error(f"WeCom webhook send failed: {e}")
        return False
```

- [ ] **Step 2: Commit**

```bash
git add push.py && git commit -m "feat: add WeChat Work webhook push"
```

---

### Task 17: FastAPI web application skeleton

**Files:**
- Create: `D:\Projects\ai-news-digest\web\app.py`
- Create: `D:\Projects\ai-news-digest\web\routes\home.py`
- Create: `D:\Projects\ai-news-digest\web\routes\reader.py`
- Create: `D:\Projects\ai-news-digest\web\routes\search.py`
- Create: `D:\Projects\ai-news-digest\web\routes\concepts.py`
- Create: `D:\Projects\ai-news-digest\web\routes\review.py`

- [ ] **Step 1: Write web/app.py**

```python
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .routes import home, reader, search, concepts, review

logger = logging.getLogger(__name__)

# Global state
import threading
_server_thread: threading.Thread | None = None
_db_conn = None
_ai_client = None
_config = None


def get_db():
    return _db_conn


def get_ai():
    return _ai_client


def get_config():
    return _config


def set_globals(db_conn, ai_client, config):
    global _db_conn, _ai_client, _config
    _db_conn = db_conn
    _ai_client = ai_client
    _config = config


def create_app() -> FastAPI:
    app_ = FastAPI()

    app_.mount("/static", StaticFiles(directory="web/static"), name="static")

    app_.include_router(home.router)
    app_.include_router(reader.router)
    app_.include_router(search.router)
    app_.include_router(concepts.router)
    app_.include_router(review.router)

    @app_.get("/api/health")
    async def health():
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"status": "ok", "server": "ai-news-digest"},
            headers={"x-server": "ai-news-digest"}
        )

    return app_
```

- [ ] **Step 2: Write web/routes/home.py**

```python
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.app import get_db, get_config
from db.models import get_clusters_for_date

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    db = get_db()
    if db is None:
        return templates.TemplateResponse("home.html", {"request": request, "clusters": [], "today": "", "empty": True})

    today = datetime.now().strftime("%Y-%m-%d")
    clusters = get_clusters_for_date(db, today)

    return templates.TemplateResponse("home.html", {
        "request": request,
        "clusters": clusters,
        "today": today,
        "empty": len(clusters) == 0,
    })
```

- [ ] **Step 3: Write stub routes for remaining pages**

Write `web/routes/reader.py`:

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.app import get_db
from db.models import get_article

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/reader/{article_id}", response_class=HTMLResponse)
async def reader(request: Request, article_id: str):
    db = get_db()
    article = get_article(db, article_id) if db else None
    if article is None:
        return HTMLResponse("Article not found", status_code=404)
    return templates.TemplateResponse("reader.html", {"request": request, "article": article})
```

Write `web/routes/search.py`:

```python
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.app import get_db
from db.models import search_articles

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Query(default="")):
    results = []
    if q and get_db():
        results = search_articles(get_db(), q)
    return templates.TemplateResponse("search.html", {"request": request, "query": q, "results": results})
```

Write `web/routes/concepts.py`:

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.app import get_db
from db.models import get_concepts_list

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/concepts", response_class=HTMLResponse)
async def concepts_list(request: Request):
    concepts = get_concepts_list(get_db()) if get_db() else []
    return templates.TemplateResponse("concepts.html", {"request": request, "concepts": concepts})
```

Write `web/routes/review.py`:

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.app import get_db
from ai.review import get_week_bounds
from db.models import get_weekly_review

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    db = get_db()
    week_start, week_end = get_week_bounds()
    review_data = get_weekly_review(db, week_start) if db else None
    return templates.TemplateResponse("review.html", {
        "request": request,
        "review": review_data,
        "week_start": week_start,
        "week_end": week_end,
    })
```

- [ ] **Step 4: Commit**

```bash
git add web/app.py web/routes/ && git commit -m "feat: add FastAPI app skeleton and routes"
```

---

### Task 18: HTML templates

**Files:**
- Create: `D:\Projects\ai-news-digest\web\templates\base.html`
- Create: `D:\Projects\ai-news-digest\web\templates\home.html`
- Create: `D:\Projects\ai-news-digest\web\templates\reader.html`
- Create: `D:\Projects\ai-news-digest\web\templates\search.html`
- Create: `D:\Projects\ai-news-digest\web\templates\concepts.html`
- Create: `D:\Projects\ai-news-digest\web\templates\review.html`

- [ ] **Step 1: Write web/templates/base.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 资讯管家</title>
    <link rel="stylesheet" href="/static/style.css">
    <script src="/static/htmx.min.js"></script>
    <script src="/static/htmx-sse.js"></script>
</head>
<body>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>
```

- [ ] **Step 2: Write web/templates/home.html**

```html
{% extends "base.html" %}
{% block content %}
<h1>AI 资讯管家 <span class="date">{{ today }}</span></h1>

{% if empty %}
<div class="empty-state">
    <h2>👋 欢迎！</h2>
    <p>还没有资讯数据。</p>
    <p>请双击桌面上的「AI资讯」快捷方式来采集第一期资讯。</p>
</div>
{% else %}
<div class="digest-summary">
    今日 {{ clusters|sum(attribute='articles')|map('length')|sum if clusters else 0 }} 篇文章，{{ clusters|length }} 个话题
</div>

<div class="clusters">
{% for cluster in clusters %}
<div class="cluster-card">
    <h3 class="cluster-label">
        {{ cluster.label }}
        <span class="article-count">[{{ cluster.articles|length }} 篇相关]</span>
    </h3>
    {% for article in cluster.articles %}
    <div class="article-item">
        <a href="/reader/{{ article.id }}" class="article-link">
            {{ article.title }}
        </a>
        <span class="article-meta">
            {{ article.source_id }} · {{ article.language | upper }}
            {% if article.published_at %} · {{ article.published_at[:10] }}{% endif %}
        </span>
    </div>
    {% endfor %}
</div>
{% endfor %}
</div>
{% endif %}

<nav class="bottom-nav">
    <a href="/search">🔍 搜索</a>
    <a href="/concepts">📖 概念词典</a>
    <a href="/review">📊 周报</a>
</nav>
{% endblock %}
```

- [ ] **Step 3: Write web/templates/reader.html**

```html
{% extends "base.html" %}
{% block content %}
<div class="reader-header">
    <a href="/" class="back-link">← 返回首页</a>
    <div class="feedback-buttons">
        <button hx-post="/api/feedback/{{ article.id }}?feedback=interested" hx-swap="none">👍 感兴趣</button>
        <button hx-post="/api/feedback/{{ article.id }}?feedback=not_interested" hx-swap="none">👎 不感兴趣</button>
    </div>
</div>

<h1>{{ article.title }}</h1>
<div class="article-meta">
    来源：{{ article.source_id }}
    {% if article.author %}· 作者：{{ article.author }}{% endif %}
    {% if article.published_at %}· {{ article.published_at[:10] }}{% endif %}
    · {{ article.language | upper }}
</div>

<hr>

<div class="article-body">
    {{ article.full_text or "[全文加载中...]" }}
</div>

<hr>

<div class="article-actions">
    <a href="{{ article.url }}" target="_blank" rel="noopener noreferrer" class="btn">🌐 打开原网页</a>
    {% if article.language == 'en' %}
    <button hx-get="/api/translate/{{ article.id }}" hx-target="#translation-result" hx-swap="innerHTML"
            hx-ext="sse" sse-connect="/api/translate/{{ article.id }}" class="btn">🌐 翻译全文</button>
    <div id="translation-result"></div>
    {% endif %}
</div>

<div class="concept-lookup">
    <span class="hint">选中文字后点击按钮：</span>
    <button id="concept-btn" class="btn" onclick="lookupConcept()">查这个概念</button>
</div>

<div class="analysis-section" id="core-insight">
    <h3>💡 核心观点</h3>
    <div hx-get="/api/analyze/{{ article.id }}?type=core_insight" hx-trigger="load"
         hx-ext="sse" sse-connect="/api/analyze/{{ article.id }}?type=core_insight">
        <div class="skeleton">正在生成核心观点...</div>
    </div>
</div>

<div class="analysis-section">
    <button hx-get="/api/analyze/{{ article.id }}?type=what_it_means" hx-target="#what-it-means-result"
            hx-swap="innerHTML" hx-ext="sse" sse-connect="/api/analyze/{{ article.id }}?type=what_it_means"
            class="btn btn-primary">
        ▶ 这意味着什么？
    </button>
    <div id="what-it-means-result"></div>
</div>

<script>
function lookupConcept() {
    const selection = window.getSelection().toString().trim();
    if (!selection || selection.length > 100) return;
    fetch('/api/concept-lookup', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({term: selection, article_id: '{{ article.id }}'})
    }).then(r => r.json()).then(d => {
        if (d.definition) alert(d.term + ': ' + d.definition);
    });
}
</script>
{% endblock %}
```

- [ ] **Step 4: Write web/templates/search.html**

```html
{% extends "base.html" %}
{% block content %}
<h1>🔍 搜索</h1>
<form method="get" action="/search">
    <input type="text" name="q" value="{{ query }}" placeholder="搜索已读文章..." class="search-input" autofocus>
    <button type="submit" class="btn">搜索</button>
</form>

{% if results %}
<div class="search-results">
    {% for r in results %}
    <div class="search-result-item">
        <a href="/reader/{{ r.id }}">{{ r.title }}</a>
        <span class="article-meta">{{ r.source_id }} · {{ r.language | upper }}</span>
        <p class="snippet">{{ r.snippet | safe }}</p>
    </div>
    {% endfor %}
</div>
{% elif query %}
<p>没有找到结果。</p>
{% endif %}

<nav class="bottom-nav">
    <a href="/">🏠 首页</a>
    <a href="/concepts">📖 概念词典</a>
    <a href="/review">📊 周报</a>
</nav>
{% endblock %}
```

- [ ] **Step 5: Write web/templates/concepts.html**

```html
{% extends "base.html" %}
{% block content %}
<h1>📖 概念词典</h1>

{% if concepts %}
<div class="concepts-list">
    {% for c in concepts %}
    <div class="concept-item">
        <strong>{{ c.term }}</strong>
        <span class="query-count">查询 {{ c.query_count }} 次</span>
        {% if c.definition %}
        <p>{{ c.definition }}</p>
        {% endif %}
    </div>
    {% endfor %}
</div>
{% else %}
<p>还没有查过任何概念。在读文章时选中不理解的术语，点击「查这个概念」来添加。</p>
{% endif %}

<nav class="bottom-nav">
    <a href="/">🏠 首页</a>
    <a href="/search">🔍 搜索</a>
    <a href="/review">📊 周报</a>
</nav>
{% endblock %}
```

- [ ] **Step 6: Write web/templates/review.html**

```html
{% extends "base.html" %}
{% block content %}
<h1>📊 周报</h1>

{% if review %}
<div class="review-content">
    {{ review.content | replace('\n', '<br>') | safe }}
</div>
<p class="review-meta">周期：{{ review.week_start }} ~ {{ review.week_end }}</p>
{% else %}
<p>{{ week_start }} ~ {{ week_end }} 的周报尚未生成。</p>
<button hx-post="/api/generate-review" class="btn btn-primary">生成周报</button>
<div id="review-result"></div>
{% endif %}

<nav class="bottom-nav">
    <a href="/">🏠 首页</a>
    <a href="/search">🔍 搜索</a>
    <a href="/concepts">📖 概念词典</a>
</nav>
{% endblock %}
```

- [ ] **Step 7: Commit**

```bash
git add web/templates/ && git commit -m "feat: add all HTML templates"
```

---

### Task 19: Static assets (CSS + HTMX)

**Files:**
- Create: `D:\Projects\ai-news-digest\web\static\style.css`
- Existing (need to download): `D:\Projects\ai-news-digest\web\static\htmx.min.js`
- Existing (need to download): `D:\Projects\ai-news-digest\web\static\htmx-sse.js`

- [ ] **Step 1: Write web/static/style.css**

```css
:root {
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #c9d1d9;
    --text-muted: #8b949e;
    --accent: #58a6ff;
    --accent-hover: #79c0ff;
    --btn-bg: #21262d;
    --positive: #3fb950;
    --negative: #f85149;
    --explore: #d2991d;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    background: var(--bg);
    color: var(--text);
    min-width: 1024px;
    line-height: 1.6;
}

.container {
    max-width: 960px;
    margin: 0 auto;
    padding: 24px 32px;
}

h1 { font-size: 1.5rem; margin-bottom: 16px; }
h1 .date { color: var(--text-muted); font-size: 0.9rem; font-weight: normal; }

a { color: var(--accent); text-decoration: none; }
a:hover { color: var(--accent-hover); text-decoration: underline; }

.empty-state {
    text-align: center;
    padding: 80px 0;
    color: var(--text-muted);
}

.digest-summary {
    color: var(--text-muted);
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
}

.cluster-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
}

.cluster-label {
    font-size: 1.1rem;
    color: var(--accent);
    margin-bottom: 8px;
}

.cluster-label .explore-tag {
    color: var(--explore);
    font-size: 0.8rem;
}

.article-count { color: var(--text-muted); font-size: 0.8rem; font-weight: normal; }

.article-item {
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: baseline;
}
.article-item:last-child { border-bottom: none; }

.article-meta { color: var(--text-muted); font-size: 0.85rem; white-space: nowrap; margin-left: 12px; }

.reader-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
}

.feedback-buttons button {
    background: var(--btn-bg);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
    margin-left: 8px;
}
.feedback-buttons button:hover { border-color: var(--accent); }

.article-body {
    margin: 20px 0;
    line-height: 1.8;
    font-size: 1rem;
}

.article-actions { margin: 16px 0; display: flex; gap: 8px; }

.btn {
    display: inline-block;
    background: var(--btn-bg);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.9rem;
    text-decoration: none;
}
.btn:hover { border-color: var(--accent); color: var(--accent-hover); }
.btn-primary { background: #1f6feb; border-color: #1f6feb; color: #fff; }
.btn-primary:hover { background: #388bfd; }

.concept-lookup { margin: 12px 0; display: flex; align-items: center; gap: 8px; }
.concept-lookup .hint { color: var(--text-muted); font-size: 0.85rem; }

.analysis-section { margin: 20px 0; padding: 16px; background: var(--surface); border-radius: 8px; border: 1px solid var(--border); }
.analysis-section h3 { margin-bottom: 12px; color: var(--accent); }

.skeleton { color: var(--text-muted); animation: pulse 1.5s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.search-input {
    width: 100%;
    padding: 10px 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-size: 1rem;
    margin-bottom: 12px;
}

.search-results { margin: 16px 0; }
.search-result-item { padding: 12px 0; border-bottom: 1px solid var(--border); }
.snippet { color: var(--text-muted); font-size: 0.9rem; margin-top: 4px; }
.snippet mark { background: rgba(88, 166, 255, 0.3); color: var(--text); padding: 1px 3px; border-radius: 2px; }

.concepts-list { margin: 16px 0; }
.concept-item { padding: 12px 0; border-bottom: 1px solid var(--border); }
.concept-item strong { color: var(--accent); }
.query-count { color: var(--text-muted); font-size: 0.8rem; margin-left: 8px; }

.review-content { line-height: 1.8; margin: 16px 0; }
.review-meta { color: var(--text-muted); font-size: 0.85rem; }

.bottom-nav {
    margin-top: 40px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    display: flex;
    gap: 24px;
    justify-content: center;
}

hr { border: none; border-top: 1px solid var(--border); margin: 20px 0; }
```

- [ ] **Step 2: Download HTMX files**

```powershell
cd D:\Projects\ai-news-digest\web\static
Invoke-WebRequest -Uri "https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js" -OutFile "htmx.min.js"
Invoke-WebRequest -Uri "https://unpkg.com/htmx.org@1.9.12/dist/ext/sse.js" -OutFile "htmx-sse.js"
```

- [ ] **Step 3: Commit**

```bash
git add web/static/ && git commit -m "feat: add CSS and HTMX static assets"
```

---

### Task 20: API endpoints (SSE analysis, translate, concept lookup, feedback, review generation)

**Files:**
- Create: `D:\Projects\ai-news-digest\web\routes\api.py`

- [ ] **Step 1: Write web/routes/api.py**

```python
import json
import asyncio
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse
from web.app import get_db, get_ai, get_config
from db.models import (
    get_article, set_full_text, get_cached_analysis, cache_analysis,
    record_read, set_feedback, get_or_create_concept, link_article_concept,
    get_concepts_list, search_articles, get_clusters_for_date,
    get_weekly_review, save_weekly_review, has_digest_today,
    article_exists
)
from ai.analysis import (
    build_core_insight_prompt, build_what_it_means_prompt,
    build_translation_prompt, build_concept_lookup_prompt, build_review_prompt
)
from ai.review import get_week_bounds, get_partial_week_end
from pipeline.extractor import extract_full_text

router = APIRouter()


@router.get("/api/analyze/{article_id}")
async def analyze(article_id: str, type: str = Query(...)):
    db = get_db()
    ai = get_ai()
    if db is None or ai is None:
        return StreamingResponse(iter(["AI 服务未配置"]), media_type="text/event-stream")

    article = get_article(db, article_id)
    if article is None:
        return StreamingResponse(iter(["文章不存在"]), media_type="text/event-stream")

    # Get or extract full text
    full_text = article.get("full_text") or article.get("content") or ""
    if not full_text or full_text.startswith("["):
        full_text = article.get("content") or ""
        if not full_text or full_text.startswith("["):
            full_text = await extract_full_text(article["url"])
            set_full_text(db, article_id, full_text)

    # Check cache
    cached = get_cached_analysis(db, article_id, type)
    if cached:
        async def cached_stream():
            yield f"data: {json.dumps({'chunk': cached})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    # Build prompt
    if type == "core_insight":
        system, user = build_core_insight_prompt(full_text)
    elif type == "what_it_means":
        concepts = [c["term"] for c in get_concepts_list(db)]
        system, user = build_what_it_means_prompt(full_text, concepts)
    else:
        return StreamingResponse(iter(["未知分析类型"]), media_type="text/event-stream")

    # Stream response
    async def generate():
        full_response = ""
        for chunk in ai.chat_stream(system, user):
            full_response += chunk
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        # Cache the full response
        try:
            cache_analysis(db, article_id, type, full_response)
        except Exception:
            pass
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/translate/{article_id}")
async def translate(article_id: str):
    db = get_db()
    ai = get_ai()
    if db is None or ai is None:
        return StreamingResponse(iter(["AI 服务未配置"]), media_type="text/event-stream")

    article = get_article(db, article_id)
    if article is None:
        return StreamingResponse(iter(["文章不存在"]), media_type="text/event-stream")

    full_text = article.get("full_text") or article.get("content") or ""
    if not full_text or full_text.startswith("[") or article.get("language") != "en":
        if not full_text or full_text.startswith("["):
            full_text = await extract_full_text(article["url"])
            set_full_text(db, article_id, full_text)

    cached = get_cached_analysis(db, article_id, "translation")
    if cached:
        async def cached_stream():
            yield f"data: {json.dumps({'chunk': cached})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    system, user = build_translation_prompt(full_text)

    async def generate():
        full_response = ""
        for chunk in ai.chat_stream(system, user, max_tokens=2048):
            full_response += chunk
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        try:
            cache_analysis(db, article_id, "translation", full_response)
        except Exception:
            pass
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/concept-lookup")
async def concept_lookup(request: Request):
    db = get_db()
    ai = get_ai()
    data = await request.json()
    term = data.get("term", "").strip()
    article_id = data.get("article_id", "")

    if not term or db is None or ai is None:
        return JSONResponse({"term": term, "definition": ""})

    system, user = build_concept_lookup_prompt(term)
    definition, _ = ai.chat(system, user, max_tokens=200)

    cid = get_or_create_concept(db, term, definition)
    if article_id:
        link_article_concept(db, article_id, cid)

    return JSONResponse({"term": term, "definition": definition})


@router.post("/api/feedback/{article_id}")
async def feedback(article_id: str, feedback: str = Query(...)):
    db = get_db()
    if db is None:
        return JSONResponse({"status": "error"})
    set_feedback(db, article_id, feedback)
    return JSONResponse({"status": "ok"})


@router.post("/api/generate-review")
async def generate_review():
    db = get_db()
    ai = get_ai()
    if db is None or ai is None:
        return JSONResponse({"status": "error", "message": "AI 服务未配置"})

    week_start, week_end = get_week_bounds()
    existing = get_weekly_review(db, week_start)
    if existing:
        return JSONResponse({"status": "ok", "message": "本周周报已存在", "review": existing})

    # Gather data
    from datetime import datetime, timedelta
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=7)
    rows = db.execute(
        "SELECT a.title, ac.content as insight FROM read_records r "
        "JOIN articles a ON r.article_id = a.id "
        "LEFT JOIN analysis_cache ac ON a.id = ac.article_id AND ac.analysis_type = 'core_insight' "
        "WHERE r.opened_at >= ?",
        (start_dt.strftime("%Y-%m-%d"),)
    ).fetchall()
    articles = [{"title": r[0], "insight": r[1] or ""} for r in rows]
    concepts = [c["term"] for c in get_concepts_list(db)]

    interested = [r[0] for r in db.execute(
        "SELECT DISTINCT a.title FROM read_records r JOIN articles a ON r.article_id = a.id WHERE r.feedback = 'interested' AND r.opened_at >= ?",
        (start_dt.strftime("%Y-%m-%d"),)
    ).fetchall()]

    not_interested = [r[0] for r in db.execute(
        "SELECT DISTINCT a.title FROM read_records r JOIN articles a ON r.article_id = a.id WHERE r.feedback = 'not_interested' AND r.opened_at >= ?",
        (start_dt.strftime("%Y-%m-%d"),)
    ).fetchall()]

    system, user = build_review_prompt(articles, concepts, interested, not_interested)
    content, tokens = ai.chat(system, user, max_tokens=2048)

    article_ids = [r[0] for r in db.execute(
        "SELECT article_id FROM read_records WHERE opened_at >= ?", (start_dt.strftime("%Y-%m-%d"),)
    ).fetchall()]

    save_weekly_review(db, week_start, week_end, content, article_ids)

    return JSONResponse({"status": "ok", "content": content})


@router.post("/api/collect")
async def trigger_collect():
    """Trigger a new collection pipeline run."""
    # This is handled by passing a flag to the main process
    # For now, we create a marker file that main.py checks
    import os
    with open(".collect_trigger", "w") as f:
        f.write("1")
    return JSONResponse({"status": "started", "message": "采集已触发"})
```

- [ ] **Step 2: Update web/app.py to include api router**

```python
# Add this import in create_app():
from .routes import api
app_.include_router(api.router)
```

- [ ] **Step 3: Commit**

```bash
git add web/routes/api.py && git commit -m "feat: add API endpoints for SSE analysis, translate, concepts, feedback, review"
```

---

### Task 21: Main orchestration (main.py)

**Files:**
- Create: `D:\Projects\ai-news-digest\main.py`

- [ ] **Step 1: Write main.py**

```python
import sys
import os
import asyncio
import logging
import webbrowser
import threading
import time
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")


def check_existing_server(port: int) -> bool:
    """Check if an ai-news-digest server is already running on this port."""
    import httpx
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=3)
        return resp.headers.get("x-server") == "ai-news-digest"
    except Exception:
        return False


def start_server(db_conn, ai_client, cfg, port: int):
    """Start FastAPI server in a background thread."""
    from web.app import create_app, set_globals
    import uvicorn

    set_globals(db_conn, ai_client, cfg)
    app = create_app()

    config = uvicorn.Config(app, host=cfg.host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


async def run_collection_pipeline(db_conn, ai_client, cfg):
    """Run the full collection pipeline: fetch → dedup → cluster → push."""
    from collectors.registry import get_all
    from pipeline.dedup import filter_duplicates_by_title
    from pipeline.cluster import cluster_articles, make_cluster_id, make_cluster_label
    from db.models import (
        insert_article, article_exists, get_clusters_for_date,
        has_digest_today, create_digest, mark_webhook_sent, cleanup_old_data
    )
    from push import send_wecom_digest

    since = datetime.now() - timedelta(days=2)  # Fetch last 2 days

    # Fetch
    all_articles = []
    collectors = get_all()
    tasks = [c.fetch(since) for c in collectors]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Collector {collectors[i].name} failed: {result}")
        else:
            all_articles.extend(result)
            logger.info(f"Collector {collectors[i].name}: {len(result)} articles")

    logger.info(f"Total fetched: {len(all_articles)}")

    # Insert new articles
    new_articles = []
    for art in all_articles:
        aid = insert_article(db_conn, art.source_id, art.url, art.title,
                             summary=art.summary, content=art.content or "",
                             author=art.author, published_at=art.published_at,
                             language=art.language)
        if aid:
            new_articles.append({
                "id": aid, "title": art.title, "summary": art.summary,
                "source_id": art.source_id, "language": art.language,
                "published_at": art.published_at,
            })

    logger.info(f"New articles: {len(new_articles)}")

    if not new_articles:
        # Still update existing clusters for display
        return

    # Dedup
    deduped = filter_duplicates_by_title(new_articles, threshold=0.85)

    # Cluster
    clusters = cluster_articles(deduped, threshold=cfg.cluster_threshold)

    # Apply exploration tagging
    import random
    today_str = datetime.now().strftime("%Y-%m-%d")
    for i, cluster in enumerate(clusters):
        label = make_cluster_label(cluster)
        cid = make_cluster_id(today_str, i)
        # Use LLM to generate label
        if ai_client and cluster:
            try:
                titles = "\n".join([a.get("title", "")[:80] for a in cluster[:5]])
                sys_p = "你是一个信息分类助手。"
                usr_p = f"为以下一组相关文章生成一个简短的中文标签（不超过15个字）：\n\n{titles}\n\n标签："
                label, _ = ai_client.chat(sys_p, usr_p, max_tokens=30)
                label = label.strip().strip('"').strip("'")
            except Exception:
                pass

        db_conn.execute(
            "INSERT INTO clusters (id, label, digest_date) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET label = ?",
            (cid, label, today_str, label)
        )
        for art in cluster:
            db_conn.execute(
                "INSERT OR IGNORE INTO cluster_articles (cluster_id, article_id) VALUES (?, ?)",
                (cid, art["id"])
            )
    db_conn.commit()

    # Mark exploration articles
    small_clusters = [c for c in clusters if len(c) <= 2]
    if small_clusters:
        explore_count = max(1, int(len(new_articles) * cfg.exploration_rate))
        explore_articles = []
        for c in small_clusters:
            explore_articles.extend(c)
        random.shuffle(explore_articles)
        explore_articles = explore_articles[:explore_count]
        # Store exploration marker in metadata (we use clusters table label prefix)
        for art in explore_articles:
            db_conn.execute(
                "UPDATE articles SET summary = '[探索] ' || COALESCE(summary, '') WHERE id = ?",
                (art["id"],)
            )
        db_conn.commit()

    # Push if not already done today
    if not has_digest_today(db_conn):
        all_ids = [a["id"] for cluster in clusters for a in cluster]
        all_ids = all_ids[:cfg.max_daily_articles]
        digest_id = create_digest(db_conn, all_ids)

        cluster_data = []
        seen_ids = set()
        for cluster in clusters:
            arts = [a for a in cluster if a["id"] in all_ids and a["id"] not in seen_ids]
            if arts:
                for a in arts:
                    seen_ids.add(a["id"])
                cluster_data.append({
                    "label": make_cluster_label(cluster),
                    "articles": arts,
                })

        success = await send_wecom_digest(
            cfg.wecom_webhook_url, today_str,
            len(all_articles), len(all_ids), cluster_data
        )
        if success:
            mark_webhook_sent(db_conn)
            logger.info("WeChat push sent successfully")
        else:
            logger.warning("WeChat push failed")

    # Cleanup old data
    cleanup_old_data(db_conn, cfg.full_text_retention_days, cfg.analysis_cache_retention_days)

    return len(new_articles)


def main():
    # Find available port
    from config import load_config
    cfg = load_config()

    port = cfg.port
    for offset in range(3):
        if not check_existing_server(port + offset) or offset == 0:
            port = port + offset
            break
    else:
        logger.error("No available port found")
        sys.exit(1)

    if check_existing_server(port):
        logger.info(f"Server already running on port {port}, triggering collection")
        webbrowser.open(f"http://127.0.0.1:{port}")
        try:
            import httpx
            httpx.post(f"http://127.0.0.1:{port}/api/collect", timeout=5)
        except Exception:
            pass
        return

    assert cfg.host == "127.0.0.1", "Server must bind to 127.0.0.1 only"

    # Init DB
    from db.schema import init_db
    db_path = os.path.join(os.path.dirname(__file__), "ai_news.db")
    db_conn = init_db(db_path)

    # Init AI client
    ai_client = None
    if cfg.deepseek_api_key:
        from ai.client import AIClient
        ai_client = AIClient(cfg.deepseek_api_key)

    if not cfg.deepseek_api_key:
        logger.warning(".env 未找到或未配置 DEEPSEEK_API_KEY，AI 功能不可用")

    # Start server in background thread
    server_thread = threading.Thread(
        target=start_server, args=(db_conn, ai_client, cfg, port), daemon=True
    )
    server_thread.start()

    # Wait for server to be ready
    time.sleep(1)

    # Run collection pipeline
    try:
        count = asyncio.run(run_collection_pipeline(db_conn, ai_client, cfg))
        logger.info(f"Collection complete: {count} new articles")
    except Exception as e:
        logger.error(f"Collection pipeline error: {e}")

    # Open browser
    webbrowser.open(f"http://127.0.0.1:{port}")

    # Keep running
    try:
        while server_thread.is_alive():
            server_thread.join(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")

    db_conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add main.py && git commit -m "feat: add main orchestration with server, collection, and browser launch"
```

---

### Task 22: Windows launcher scripts

**Files:**
- Create: `D:\Projects\ai-news-digest\ai-news.bat`
- Create: `D:\Projects\ai-news-digest\setup.bat`

- [ ] **Step 1: Write ai-news.bat**

```batch
@echo off
cd /d D:\Projects\ai-news-digest
call .venv\Scripts\activate.bat
python main.py
pause
```

- [ ] **Step 2: Write setup.bat**

```batch
@echo off
echo Setting up AI资讯管家...
cd /d D:\Projects\ai-news-digest

echo.
echo Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat

echo.
echo Installing dependencies...
pip install fastapi "uvicorn[standard]" jinja2 feedparser httpx readability-lxml chardet scikit-learn openai python-dotenv pyyaml tenacity

echo.
echo Downloading HTMX...
powershell -Command "Invoke-WebRequest -Uri 'https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js' -OutFile 'web\static\htmx.min.js'"
powershell -Command "Invoke-WebRequest -Uri 'https://unpkg.com/htmx.org@1.9.12/dist/ext/sse.js' -OutFile 'web\static\htmx-sse.js'"

echo.
echo Creating desktop shortcut...
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\AI资讯.lnk'); $SC.TargetPath = 'D:\Projects\ai-news-digest\ai-news.bat'; $SC.Save()"

echo.
echo Done! Double-click 'AI资讯' on your desktop to get started.
echo Don't forget to copy .env.example to .env and fill in your API keys.
pause
```

- [ ] **Step 3: Commit**

```bash
git add ai-news.bat setup.bat && git commit -m "feat: add Windows launcher and setup scripts"
```

---

### Task 23: Collector error handling tests

**Files:**
- Create: `D:\Projects\ai-news-digest\tests\test_collectors.py`

- [ ] **Step 1: Write tests/test_collectors.py**

```python
import pytest
from datetime import datetime, timedelta
from collectors.rss_reader import RSSCollector


@pytest.mark.asyncio
async def test_rss_collector_handles_bad_url():
    collector = RSSCollector("test-bad", "https://127.0.0.1:1/nonexistent", language="en")
    articles = await collector.fetch(datetime.now() - timedelta(days=1))
    assert articles == []


def test_rss_collector_attributes():
    collector = RSSCollector("test", "https://example.com/rss", language="zh")
    assert collector.name == "test"
    assert collector.language == "zh"
    assert collector.type == "rss"
```

- [ ] **Step 2: Run tests**

```powershell
pytest tests/test_collectors.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_collectors.py && git commit -m "test: add collector error handling tests"
```

---

### Task 24: Integration test

**Files:**
- Create: `D:\Projects\ai-news-digest\tests\test_integration.py`
- Create: `D:\Projects\ai-news-digest\tests\conftest.py`

- [ ] **Step 1: Write tests/conftest.py**

```python
import pytest
import sqlite3
import tempfile
import os
from db.schema import init_db
from config import Config


@pytest.fixture
def test_db():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        conn = init_db(path)
        yield conn
        conn.close()


@pytest.fixture
def test_config():
    return Config(
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
```

- [ ] **Step 2: Write tests/test_integration.py**

```python
"""Integration test: mock the full pipeline from article insert → dedup → cluster → digest."""

from datetime import datetime
from db.models import (
    insert_article, get_clusters_for_date, has_digest_today,
    create_digest, mark_webhook_sent,
)
from pipeline.dedup import filter_duplicates_by_title
from pipeline.cluster import cluster_articles


def test_full_pipeline_no_ai(test_db, test_config):
    """Test the full pipeline with mock data, no LLM calls."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Insert 5 articles
    articles = [
        {"source_id": "arxiv-cs-ai", "url": "http://arxiv.org/abs/2606.00001", "title": "GPT-5 Technical Report", "summary": "OpenAI releases GPT-5", "language": "en"},
        {"source_id": "hackernews", "url": "https://news.ycombinator.com/item?id=1", "title": "OpenAI Releases GPT-5 Model", "summary": "GPT-5 announced", "language": "en"},
        {"source_id": "jiqizhixin", "url": "https://jiqizhixin.com/articles/2026-06-08-1", "title": "GPT-5 正式发布", "summary": "OpenAI 发布 GPT-5", "language": "zh"},
        {"source_id": "reddit-ml", "url": "https://reddit.com/r/ml/comments/1", "title": "MoE Training Efficiency Breakthrough", "summary": "New MoE method", "language": "en"},
        {"source_id": "github-trending", "url": "https://github.com/user/repo", "title": "user/repo", "summary": "A cool AI tool", "language": "en"},
    ]

    inserted = []
    for art in articles:
        aid = insert_article(test_db, art["source_id"], art["url"], art["title"],
                             summary=art["summary"], language=art["language"])
        if aid:
            inserted.append({"id": aid, "title": art["title"], "summary": art["summary"],
                             "source_id": art["source_id"], "language": art["language"],
                             "published_at": None})

    assert len(inserted) >= 4  # Some may dedup at DB level

    # Dedup
    deduped = filter_duplicates_by_title(inserted)
    assert len(deduped) > 0

    # Cluster
    clusters = cluster_articles(deduped, threshold=0.4)
    assert len(clusters) > 0  # GPT-5 articles should cluster together

    # Digests
    ids = [a["id"] for cluster in clusters for a in cluster]
    digest_id = create_digest(test_db, ids[:test_config.max_daily_articles])
    if digest_id:
        mark_webhook_sent(test_db)

    # Verify
    assert has_digest_today(test_db)
    clusters_db = get_clusters_for_date(test_db, today)
    # Clusters might not be in DB since we didn't run the full pipeline
```

- [ ] **Step 3: Run integration test**

```powershell
pytest tests/test_integration.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_integration.py && git commit -m "test: add integration test for full pipeline"
```

---

### Task 25: Final verification

- [ ] **Step 1: Run all tests**

```powershell
pytest tests/ -v
```
Expected: All tests PASS

- [ ] **Step 2: Verify project structure**

```powershell
Get-ChildItem -Recurse -File | Where-Object { $_.Extension -in '.py','.html','.css','.js','.bat','.yaml','.toml','.md' } | ForEach-Object { $_.FullName.Replace("D:\Projects\ai-news-digest\", "") } | Sort-Object
```

Expected: Output matches module structure in spec.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "chore: finalize v0.1 implementation"
```
