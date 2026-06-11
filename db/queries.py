import re
import sqlite3
import json


def get_available_dates(conn: sqlite3.Connection, limit: int = 30) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT digest_date FROM clusters ORDER BY digest_date DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [r[0] for r in rows]


def get_clusters_for_date(conn: sqlite3.Connection, date_str: str) -> list[dict]:
    rows = conn.execute(
        "SELECT c.id as cluster_id, c.label, a.id, a.title, a.source_id, "
        "a.language, a.published_at, a.summary "
        "FROM clusters c "
        "JOIN cluster_articles ca ON ca.cluster_id = c.id "
        "JOIN articles a ON ca.article_id = a.id "
        "WHERE c.digest_date = ? "
        "ORDER BY c.id, a.published_at DESC",
        (date_str,)
    ).fetchall()
    result: dict[int, dict] = {}
    for row in rows:
        cid = row[0]
        if cid not in result:
            result[cid] = {"label": row[1], "articles": []}
        result[cid]["articles"].append({
            "id": row[2], "title": row[3], "source_id": row[4],
            "language": row[5], "published_at": row[6], "summary": row[7] or "",
        })
    return list(result.values())


def _sanitize_fts5_query(query: str) -> str:
    clean = re.sub(r'[*"()+\-]', ' ', query)
    clean = ' '.join(clean.split())
    if not clean:
        return '""'
    return '"' + clean + '"'


def search_articles(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    safe_query = _sanitize_fts5_query(query)
    try:
        rows = conn.execute(
            "SELECT a.id, a.title, a.source_id, a.language, a.published_at, "
            "snippet(articles_fts, 1, '<mark>', '</mark>', '...', 32) as snippet "
            "FROM articles_fts f JOIN articles a ON a._rowid_ = f.rowid "
            "WHERE articles_fts MATCH ? ORDER BY rank LIMIT ?",
            (safe_query, limit)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{
        "id": r[0], "title": r[1], "source_id": r[2],
        "language": r[3], "published_at": r[4], "snippet": r[5],
    } for r in rows]


def get_weekly_review(conn: sqlite3.Connection, week_start: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM weekly_reviews WHERE week_start = ?",
        (week_start,)
    ).fetchone()
    if not row:
        return None
    col_names = [c[1] for c in conn.execute("PRAGMA table_info(weekly_reviews)").fetchall()]
    d = dict(zip(col_names, row))
    try:
        d["article_ids"] = json.loads(d.get("article_ids", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["article_ids"] = []
    return d


def save_weekly_review(conn: sqlite3.Connection, week_start: str, week_end: str,
                       content: str, article_ids: list[str],
                       commit: bool = True):
    ids_json = json.dumps(article_ids)
    conn.execute(
        "INSERT INTO weekly_reviews (week_start, week_end, content, article_ids) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(week_start) DO UPDATE SET "
        "content = ?, article_ids = ?, week_end = ?",
        (week_start, week_end, content, ids_json,
         content, ids_json, week_end)
    )
    if commit:
        conn.commit()


def get_read_articles_with_insights(conn: sqlite3.Connection, since: str) -> list[dict]:
    rows = conn.execute(
        "SELECT a.title, COALESCE(ac.content, '') as insight FROM read_records r "
        "JOIN articles a ON r.article_id = a.id "
        "LEFT JOIN analysis_cache ac ON a.id = ac.article_id AND ac.analysis_type = 'core_insight' "
        "WHERE r.opened_at >= ?",
        (since,)
    ).fetchall()
    return [{"title": r[0], "insight": r[1]} for r in rows]


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
