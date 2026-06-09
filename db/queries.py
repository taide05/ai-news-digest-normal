import sqlite3
import json


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
        col_names = [c[1] for c in conn.execute("PRAGMA table_info(articles)").fetchall()
                     if c[1] in ("id", "title", "source_id", "language", "published_at")]
        result.append({
            "label": row[1],
            "articles": [dict(zip(col_names, r)) for r in arts],
        })
    return result


def search_articles(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT a.id, a.title, a.source_id, a.language, a.published_at, "
        "snippet(articles_fts, 1, '<mark>', '</mark>', '...', 32) as snippet "
        "FROM articles_fts f JOIN articles a ON a._rowid_ = f.rowid "
        "WHERE articles_fts MATCH ? ORDER BY rank LIMIT ?",
        (query, limit)
    ).fetchall()
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
