from __future__ import annotations
import sqlite3

from db.url_utils import normalize_url, make_article_id
from db.queries import get_clusters_for_date, search_articles, get_weekly_review, save_weekly_review
from db.digest import has_digest_today, create_digest, mark_webhook_sent
from db.maintenance import cleanup_old_data


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
    cols = [c[1] for c in conn.execute("PRAGMA table_info(articles)")]
    return dict(zip(cols, row))


def set_full_text(conn: sqlite3.Connection, article_id: str, full_text: str):
    conn.execute("UPDATE articles SET full_text = ? WHERE id = ?", (full_text, article_id))
    conn.commit()



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


def get_all_sources(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, type, config, enabled, fail_count, last_fetch FROM sources ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def add_source(conn, sid: str, name: str, stype: str, config: str) -> bool:
    try:
        conn.execute(
            "INSERT INTO sources (id, name, type, config) VALUES (?, ?, ?, ?)",
            (sid, name, stype, config)
        )
        conn.commit()
        return True
    except Exception:
        return False


def remove_source(conn, sid: str):
    conn.execute("DELETE FROM sources WHERE id = ?", (sid,))
    conn.commit()


def toggle_source(conn, sid: str, enabled: bool):
    conn.execute("UPDATE sources SET enabled = ? WHERE id = ?", (int(enabled), sid))
    conn.commit()

