from __future__ import annotations
import json
import re
import sqlite3
from urllib.parse import urlparse

from db.url_utils import normalize_url, make_article_id
from db.queries import get_clusters_for_date, search_articles, get_weekly_review, save_weekly_review
from db.digest import has_digest_today, create_digest, mark_webhook_sent
from db.maintenance import cleanup_old_data


def article_exists(conn: sqlite3.Connection, source_id: str, url: str) -> bool:
    row = conn.execute("SELECT 1 FROM articles WHERE source_id = ? AND url = ?", (source_id, normalize_url(url))).fetchone()
    return row is not None


def insert_article(conn: sqlite3.Connection, source_id: str, url: str, title: str,
                   summary: str = "", content: str = "", author: str | None = None,
                   published_at: str | None = None, language: str = "en",
                   commit: bool = True) -> str | None:
    norm_url = normalize_url(url)
    aid = make_article_id(source_id, url)
    try:
        conn.execute(
            """INSERT INTO articles (id, source_id, url, title, summary, content, author, published_at, language)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (aid, source_id, norm_url, title, summary, content, author, published_at, language)
        )
        if commit:
            conn.commit()
        return aid
    except sqlite3.IntegrityError:
        return None


_ARTICLE_COLS = None


def get_article(conn: sqlite3.Connection, article_id: str) -> dict | None:
    global _ARTICLE_COLS
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    if row is None:
        return None
    if _ARTICLE_COLS is None:
        _ARTICLE_COLS = [c[1] for c in conn.execute("PRAGMA table_info(articles)")]
    return dict(zip(_ARTICLE_COLS, row))


def set_full_text(conn: sqlite3.Connection, article_id: str, full_text: str,
                  commit: bool = True):
    conn.execute("UPDATE articles SET full_text = ? WHERE id = ?", (full_text, article_id))
    if commit:
        conn.commit()



def record_read(conn: sqlite3.Connection, article_id: str, commit: bool = True) -> int:
    cur = conn.execute("INSERT INTO read_records (article_id) VALUES (?)", (article_id,))
    if commit:
        conn.commit()
    return cur.lastrowid


def set_feedback(conn: sqlite3.Connection, article_id: str, feedback: str,
                  commit: bool = True):
    conn.execute(
        "UPDATE read_records SET feedback = ? WHERE article_id = ? AND feedback IS NULL AND id = (SELECT MAX(id) FROM read_records WHERE article_id = ?)",
        (feedback, article_id, article_id)
    )
    if commit:
        conn.commit()


def get_or_create_concept(conn: sqlite3.Connection, term: str, definition: str = "",
                          commit: bool = True) -> int:
    row = conn.execute("SELECT id, query_count FROM concepts WHERE term = ?", (term,)).fetchone()
    if row:
        cid, count = row
        conn.execute("UPDATE concepts SET query_count = ?, last_seen = datetime('now') WHERE id = ?", (count + 1, cid))
        if definition:
            conn.execute("UPDATE concepts SET definition = ? WHERE id = ?", (definition, cid))
        if commit:
            conn.commit()
        return cid
    else:
        cur = conn.execute("INSERT INTO concepts (term, definition) VALUES (?, ?)", (term, definition))
        if commit:
            conn.commit()
        return cur.lastrowid


def link_article_concept(conn: sqlite3.Connection, article_id: str, concept_id: int,
                         commit: bool = True):
    try:
        conn.execute("INSERT INTO article_concepts (article_id, concept_id) VALUES (?, ?)", (article_id, concept_id))
        if commit:
            conn.commit()
    except sqlite3.IntegrityError:
        pass


def cache_analysis(conn: sqlite3.Connection, article_id: str, analysis_type: str,
                    content: str, model: str = "deepseek-chat", tokens_used: int = 0,
                    commit: bool = True):
    try:
        conn.execute(
            "INSERT INTO analysis_cache (article_id, analysis_type, content, model, tokens_used) VALUES (?, ?, ?, ?, ?)",
            (article_id, analysis_type, content, model, tokens_used)
        )
        if commit:
            conn.commit()
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE analysis_cache SET content = ?, tokens_used = ? WHERE article_id = ? AND analysis_type = ?",
            (content, tokens_used, article_id, analysis_type)
        )
        if commit:
            conn.commit()


def get_cached_analysis(conn: sqlite3.Connection, article_id: str, analysis_type: str) -> str | None:
    row = conn.execute("SELECT content FROM analysis_cache WHERE article_id = ? AND analysis_type = ?", (article_id, analysis_type)).fetchone()
    return row[0] if row else None


def get_concepts_list(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        "SELECT term, definition, query_count FROM concepts ORDER BY query_count DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [{"term": r[0], "definition": r[1], "query_count": r[2]} for r in rows]


def get_all_sources(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, type, config, enabled, fail_count, last_fetch FROM sources ORDER BY id"
    ).fetchall()
    cols = ["id", "name", "type", "config", "enabled", "fail_count", "last_fetch"]
    return [dict(zip(cols, r)) for r in rows]


def add_source(conn, sid: str, name: str, stype: str, config: str,
                commit: bool = True) -> bool:
    try:
        conn.execute(
            "INSERT INTO sources (id, name, type, config) VALUES (?, ?, ?, ?)",
            (sid, name, stype, config)
        )
        if commit:
            conn.commit()
        return True
    except Exception:
        return False


def remove_source(conn, sid: str, commit: bool = True):
    conn.execute("DELETE FROM sources WHERE id = ?", (sid,))
    if commit:
        conn.commit()


def toggle_source(conn, sid: str, enabled: bool, commit: bool = True):
    conn.execute("UPDATE sources SET enabled = ? WHERE id = ?", (int(enabled), sid))
    if commit:
        conn.commit()


def get_pending_candidates(conn, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT id, url, title, description, relevance_score, discovered_at "
        "FROM source_candidates WHERE verified = 0 "
        "ORDER BY relevance_score DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [{"id": r[0], "url": r[1], "title": r[2], "description": r[3],
             "relevance_score": r[4], "discovered_at": r[5]} for r in rows]


def verify_candidate(conn, candidate_id: int, commit: bool = True):
    row = conn.execute(
        "SELECT url, title FROM source_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()
    if not row:
        return
    url, title = row
    conn.execute(
        "UPDATE source_candidates SET verified = 1, confirmed_at = datetime('now') WHERE id = ?",
        (candidate_id,)
    )
    domain = urlparse(url).netloc.lower()
    sid = re.sub(r'[^a-z0-9-]', '-', domain)[:40]
    add_source(conn, f"discovered-{sid}", title or domain, "rss",
               f'{{"url": "{url}"}}', commit=False)
    if commit:
        conn.commit()


def reject_candidate(conn, candidate_id: int, commit: bool = True):
    conn.execute("DELETE FROM source_candidates WHERE id = ?", (candidate_id,))
    if commit:
        conn.commit()


def cache_cross_analysis(conn, cluster_id: str, analysis_type: str, content: str,
                         article_ids: list[str], model: str = "deepseek-chat",
                         tokens_used: int = 0, commit: bool = True):
    ids_json = json.dumps(article_ids)
    safe_content = content[:10000]
    try:
        conn.execute(
            "INSERT INTO cross_analysis_cache (cluster_id, analysis_type, content, article_ids, model, tokens_used) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cluster_id, analysis_type, safe_content, ids_json, model, tokens_used)
        )
        if commit:
            conn.commit()
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE cross_analysis_cache SET content = ?, tokens_used = ? "
            "WHERE cluster_id = ? AND analysis_type = ?",
            (safe_content, tokens_used, cluster_id, analysis_type)
        )
        if commit:
            conn.commit()


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


def get_cached_cross_analysis(conn, cluster_id: str, analysis_type: str) -> str | None:
    row = conn.execute(
        "SELECT content FROM cross_analysis_cache WHERE cluster_id = ? AND analysis_type = ?",
        (cluster_id, analysis_type)
    ).fetchone()
    return row[0] if row else None


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

