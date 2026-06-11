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


def record_rating(conn: sqlite3.Connection, article_id: str, rating: int,
                  commit: bool = True):
    """Record a 1-5 rating for an article, replacing any prior rating."""
    conn.execute(
        "INSERT OR REPLACE INTO ratings (article_id, rating, rated_at) VALUES (?, ?, datetime('now'))",
        (article_id, rating)
    )
    if commit:
        conn.commit()


def get_ratings(conn: sqlite3.Connection) -> list[dict]:
    """Return all ratings with article metadata for profile computation."""
    rows = conn.execute(
        "SELECT r.article_id, r.rating, r.rated_at, a.title, a.summary, a.source_id "
        "FROM ratings r JOIN articles a ON r.article_id = a.id "
        "ORDER BY r.rated_at DESC"
    ).fetchall()
    return [dict(zip(["article_id", "rating", "rated_at", "title", "summary", "source_id"], row))
            for row in rows]


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
        "SELECT id, name, type, config, enabled, fail_count, last_fetch, "
        "filter_keywords, hide_keywords, highlight_keywords, require_keywords "
        "FROM sources ORDER BY id"
    ).fetchall()
    cols = ["id", "name", "type", "config", "enabled", "fail_count", "last_fetch",
            "filter_keywords", "hide_keywords", "highlight_keywords", "require_keywords"]
    return [dict(zip(cols, r)) for r in rows]


def add_source(conn, sid: str, name: str, stype: str, config: str,
                filter_keywords: str = "[]", hide_keywords: str = "[]",
                highlight_keywords: str = "[]", require_keywords: str = "[]",
                commit: bool = True) -> bool:
    try:
        conn.execute(
            "INSERT INTO sources (id, name, type, config, filter_keywords, "
            "hide_keywords, highlight_keywords, require_keywords) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, name, stype, config, filter_keywords,
             hide_keywords, highlight_keywords, require_keywords)
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


def update_source_filter(conn, sid: str, filter_keywords: str, commit: bool = True):
    conn.execute("UPDATE sources SET filter_keywords = ? WHERE id = ?", (filter_keywords, sid))
    if commit:
        conn.commit()


def update_source_keywords(conn, sid: str, hide_kw: str, highlight_kw: str,
                           require_kw: str, commit: bool = True):
    conn.execute(
        "UPDATE sources SET hide_keywords=?, highlight_keywords=?, require_keywords=? WHERE id=?",
        (hide_kw, highlight_kw, require_kw, sid)
    )
    if commit:
        conn.commit()


def log_error(conn, source: str, message: str, commit: bool = True):
    conn.execute("INSERT INTO error_log (source, message) VALUES (?, ?)", (source, message[:500]))
    if commit:
        conn.commit()


def get_setting(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(conn, key: str, value: str, commit: bool = True):
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    if commit:
        conn.commit()


def record_implicit_signal(conn, article_id: str, signal_type: str, commit: bool = True):
    """Record a read/saved/dismissed signal for an article."""
    conn.execute(
        "INSERT OR IGNORE INTO implicit_signals (article_id, signal_type) VALUES (?, ?)",
        (article_id, signal_type)
    )
    if commit:
        conn.commit()


def get_implicit_signals(conn) -> list[dict]:
    """Return all implicit signals for preference computation."""
    rows = conn.execute(
        "SELECT article_id, signal_type, created_at FROM implicit_signals ORDER BY created_at DESC"
    ).fetchall()
    return [dict(zip(["article_id", "signal_type", "created_at"], row)) for row in rows]


def get_synonym_groups(conn) -> list[dict]:
    """Return all synonym groups for term expansion."""
    rows = conn.execute("SELECT id, label, terms FROM synonym_groups ORDER BY id").fetchall()
    return [{"id": row[0], "label": row[1], "terms": row[2]} for row in rows]


def get_recent_errors(conn, limit: int = 10) -> list[dict]:
    rows = conn.execute("SELECT source, message, created_at FROM error_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"source": r[0], "message": r[1], "created_at": r[2]} for r in rows]


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


def _get_weekly_concepts_by_date(conn, week_start: str, date_column: str,
                                  limit: int) -> list[dict]:
    """Unified query: get concepts filtered by a date column >= week_start."""
    assert date_column in ("last_seen", "first_seen"), f"Invalid date column: {date_column}"
    assert isinstance(week_start, str) and len(week_start) == 10, \
        f"Invalid week_start format: {week_start}"
    rows = conn.execute(
        f"SELECT term, query_count FROM concepts "
        f"WHERE {date_column} >= ? "
        f"ORDER BY query_count DESC LIMIT ?",
        (week_start, limit)
    ).fetchall()
    return [{"term": r[0], "count": r[1]} for r in rows]


def get_weekly_hot_concepts(conn, week_start: str, limit: int = 5) -> list[dict]:
    """Top concepts by query_count seen this week."""
    return _get_weekly_concepts_by_date(conn, week_start, "last_seen", limit)


def get_weekly_growing_concepts(conn, week_start: str, limit: int = 3) -> list[dict]:
    """New concepts created this week, ordered by query_count."""
    return _get_weekly_concepts_by_date(conn, week_start, "first_seen", limit)


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


def get_graph_data_from_nodes(conn, snap_date: str) -> list[dict]:
    """Return concept nodes for a given date as graph-compatible rows."""
    rows = conn.execute(
        "SELECT cn.concept_label AS concept, cn.weight AS query_count, "
        "a.id AS article_id, a.title, a.source_id "
        "FROM concept_nodes cn "
        "JOIN concepts c ON cn.concept_label = c.term "
        "JOIN article_concepts ac ON c.id = ac.concept_id "
        "JOIN articles a ON ac.article_id = a.id "
        "WHERE cn.snap_date = ? "
        "AND a.fetched_at >= ? "
        "ORDER BY cn.weight DESC LIMIT 100",
        (snap_date, snap_date)
    ).fetchall()
    return [{"article_id": r[2], "title": r[3], "source_id": r[4],
             "concept": r[0], "query_count": r[1]} for r in rows]


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


def save_graph_snapshot(conn, snap_date: str, period: str, data: dict,
                        commit: bool = True):
    """Save a graph snapshot for a given date and period."""
    data_json = json.dumps(data)
    try:
        conn.execute(
            "INSERT INTO graph_snapshots (snap_date, period, data_json) VALUES (?, ?, ?)",
            (snap_date, period, data_json)
        )
        if commit:
            conn.commit()
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE graph_snapshots SET data_json = ? WHERE snap_date = ? AND period = ?",
            (data_json, snap_date, period)
        )
        if commit:
            conn.commit()


def get_graph_snapshot(conn, snap_date: str, period: str) -> dict | None:
    """Return a saved graph snapshot, or None."""
    row = conn.execute(
        "SELECT data_json FROM graph_snapshots WHERE snap_date = ? AND period = ?",
        (snap_date, period)
    ).fetchone()
    return json.loads(row[0]) if row else None


def get_snapshot_dates(conn, limit: int = 7) -> list[str]:
    """Return recent snapshot dates, newest first."""
    rows = conn.execute(
        "SELECT DISTINCT snap_date FROM graph_snapshots "
        "ORDER BY snap_date DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [r[0] for r in rows]


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


def get_recommendations_cluster(conn, limit: int = 2) -> list[dict]:
    """Recommend articles based on recent reading topic clusters.
    Falls back to empty list if user has no recent reads.
    """
    rows = conn.execute(
        "SELECT a.id, a.title, a.source_id, c.term, COUNT(*) as matches "
        "FROM articles a "
        "JOIN article_concepts ac ON a.id = ac.article_id "
        "JOIN concepts c ON ac.concept_id = c.id "
        "WHERE ac.concept_id IN ("
        "  SELECT ac2.concept_id FROM article_concepts ac2 "
        "  JOIN read_records rr ON ac2.article_id = rr.article_id "
        "  WHERE rr.opened_at >= date('now', '-7 days')"
        "  GROUP BY ac2.concept_id ORDER BY COUNT(*) DESC LIMIT 10"
        ") "
        "AND a.id NOT IN (SELECT article_id FROM read_records) "
        "GROUP BY a.id "
        "ORDER BY matches DESC, a.fetched_at DESC "
        "LIMIT ?",
        (limit,)
    ).fetchall()
    return [{"id": r[0], "title": r[1], "source_id": r[2],
             "reason": f"近期关注「{r[3]}」"} for r in rows]


def get_recent_articles(conn, exclude_id: str, exclude_read: bool = True,
                        limit: int = 4) -> list[dict]:
    """Fallback: return recent unread articles when recommendation engines are empty."""
    if exclude_read:
        rows = conn.execute(
            "SELECT id, title, source_id FROM articles "
            "WHERE id != ? AND id NOT IN (SELECT article_id FROM read_records) "
            "ORDER BY fetched_at DESC LIMIT ?",
            (exclude_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, title, source_id FROM articles "
            "WHERE id != ? ORDER BY fetched_at DESC LIMIT ?",
            (exclude_id, limit)
        ).fetchall()
    return [{"id": r[0], "title": r[1], "source_id": r[2]} for r in rows]


# ---------------------------------------------------------------------------
#  concept_nodes — knowledge graph persistence layer
# ---------------------------------------------------------------------------

def save_concept_nodes(conn, snap_date: str, nodes: list[dict],
                       commit: bool = True):
    """Write concept nodes for a given snap_date. UPSERT by (label, date)."""
    for node in nodes:
        if node.get("type") != "concept":
            continue
        label = node["label"]
        weight = float(node.get("weight", node.get("query_count", 1)))
        article_count = node.get("article_count", 0)
        conn.execute(
            "INSERT INTO concept_nodes (concept_label, weight, article_count, "
            "first_seen_date, last_seen_date, snap_date) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(concept_label, snap_date) DO UPDATE SET "
            "weight = excluded.weight, "
            "article_count = CASE WHEN ? > 0 THEN ? ELSE concept_nodes.article_count + 1 END, "
            "last_seen_date = excluded.last_seen_date",
            (label, weight, article_count if article_count > 0 else 1,
             snap_date, snap_date, snap_date,
             article_count, article_count)
        )
    if commit:
        conn.commit()


def get_concept_nodes_by_date(conn, snap_date: str) -> list[dict]:
    """Return all concept nodes for a given snap_date."""
    rows = conn.execute(
        "SELECT id, concept_label, weight, article_count, "
        "first_seen_date, last_seen_date, lifecycle_state "
        "FROM concept_nodes WHERE snap_date = ? "
        "ORDER BY weight DESC",
        (snap_date,)
    ).fetchall()
    return [{"id": r[0], "label": r[1], "weight": r[2],
             "article_count": r[3], "first_seen_date": r[4],
             "last_seen_date": r[5], "lifecycle_state": r[6]} for r in rows]


def get_concept_node_history(conn, concept_label: str,
                              days: int = 90) -> list[dict]:
    """Return daily snapshots for a single concept, ordered by date ASC."""
    rows = conn.execute(
        "SELECT snap_date, weight, article_count, lifecycle_state "
        "FROM concept_nodes WHERE concept_label = ? "
        "AND snap_date >= date('now', ?) "
        "ORDER BY snap_date ASC",
        (concept_label, f"-{days} days")
    ).fetchall()
    return [{"snap_date": r[0], "weight": r[1],
             "article_count": r[2], "lifecycle_state": r[3]} for r in rows]


def get_distinct_concept_labels(conn, limit: int = 200) -> list[str]:
    """Return distinct concept labels seen recently."""
    rows = conn.execute(
        "SELECT DISTINCT concept_label FROM concept_nodes "
        "WHERE snap_date >= date('now', '-30 days') "
        "ORDER BY concept_label LIMIT ?",
        (limit,)
    ).fetchall()
    return [r[0] for r in rows]


def backfill_concept_nodes_from_snapshots(conn):
    """One-time: populate concept_nodes from existing graph_snapshots JSON."""
    existing = conn.execute("SELECT COUNT(*) FROM concept_nodes").fetchone()[0]
    if existing > 0:
        return 0  # Already populated

    rows = conn.execute(
        "SELECT snap_date, data_json FROM graph_snapshots ORDER BY snap_date ASC"
    ).fetchall()
    count = 0
    for snap_date, data_json in rows:
        data = json.loads(data_json)
        nodes = data.get("nodes", [])
        save_concept_nodes(conn, snap_date, nodes, commit=False)
        count += 1
    if count > 0:
        conn.commit()
    return count


def prune_stale_concepts(conn, retention_days: int = 90,
                          weight_threshold: float = 1.0,
                          commit: bool = True):
    """Delete concept snapshots older than retention_days with low weight."""
    conn.execute(
        "DELETE FROM concept_nodes WHERE snap_date < date('now', ?) "
        "AND weight < ? AND lifecycle_state = 'declining'",
        (f"-{retention_days} days", weight_threshold)
    )
    if commit:
        conn.commit()

