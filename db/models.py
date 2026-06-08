from __future__ import annotations
import sqlite3
import hashlib
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def normalize_url(url: str) -> str:
    tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source", "fbclid", "gclid"}
    parsed = urlparse(url)
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


def create_digest(conn: sqlite3.Connection, article_ids: list[str]) -> int | None:
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
