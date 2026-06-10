import logging
import math
from datetime import datetime

logger = logging.getLogger(__name__)

_profile_cache = None
_profile_cache_ts = 0


def compute_user_profile(db_conn, cfg, force_refresh: bool = False) -> dict:
    global _profile_cache, _profile_cache_ts
    now = datetime.now().timestamp()
    if not force_refresh and _profile_cache is not None and (now - _profile_cache_ts) < 300:
        return _profile_cache

    feedback_count = db_conn.execute(
        "SELECT COUNT(*) FROM read_records WHERE feedback IS NOT NULL"
    ).fetchone()[0]

    half_life = cfg.preference.half_life_days

    if feedback_count < cfg.ranking.cold_start_threshold:
        topics = {kw: 1.0 / len(cfg.preference.initial_keywords) for kw in cfg.preference.initial_keywords}
        sources = {}
    else:
        rows = db_conn.execute(
            "SELECT r.topics, r.opened_at FROM read_records r "
            "WHERE r.feedback = 'interested' AND r.topics != ''"
        ).fetchall()
        topic_counts = {}
        for topics_str, opened_at in rows:
            if not topics_str:
                continue
            try:
                opened_dt = datetime.fromisoformat(opened_at)
                days = (datetime.now() - opened_dt).days
                decay = math.exp(-days / max(1, half_life))
            except (ValueError, TypeError):
                decay = 1.0
            for t in topics_str.split(","):
                t = t.strip().lower()
                if t:
                    topic_counts[t] = topic_counts.get(t, 0) + decay
        max_count = max(topic_counts.values()) if topic_counts else 1
        topics = {t: c / max_count for t, c in topic_counts.items()}

        src_rows = db_conn.execute(
            "SELECT a.source_id, COUNT(*), SUM(CASE WHEN r.feedback='interested' THEN 1 ELSE 0 END) "
            "FROM read_records r JOIN articles a ON r.article_id = a.id "
            "WHERE r.feedback IS NOT NULL GROUP BY a.source_id"
        ).fetchall()
        sources = {}
        for src_id, total, interested in src_rows:
            sources[src_id] = interested / max(1, total)

    _profile_cache = {
        "topics": topics,
        "sources": sources,
        "feedback_count": feedback_count,
    }
    _profile_cache_ts = now
    return _profile_cache


def invalidate_profile_cache():
    global _profile_cache
    _profile_cache = None
