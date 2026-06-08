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
