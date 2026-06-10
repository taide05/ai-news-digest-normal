"""Article ranking with dual-phase strategy: cold-start -> interest-driven."""
import logging
import random
from datetime import datetime

logger = logging.getLogger("ranking")


def score_articles(db_conn, articles: list, cfg) -> list:
    """Score articles with progressive blend between cold-start and interest-driven.

    Phase 1 (feedback < cold_start_threshold): time decay + source reputation
    Phase 2 (progressive blend): interest_weight grows from 0->1 between threshold->blend_max
    """
    feedback_count = _count_feedback(db_conn)

    if feedback_count < cfg.ranking.cold_start_threshold:
        return _cold_start_score(articles, cfg)
    else:
        blend = min(1.0, max(0, (feedback_count - cfg.ranking.cold_start_threshold) / max(1, cfg.ranking.blend_max - cfg.ranking.cold_start_threshold)))
        return _blend_score(db_conn, articles, cfg, blend)


def _count_feedback(db_conn) -> int:
    cur = db_conn.execute("SELECT COUNT(*) FROM read_records WHERE feedback IS NOT NULL")
    return cur.fetchone()[0]


def _cold_start_score(articles: list, cfg) -> list:
    """Score by recency + source reputation. No AI needed."""
    now = datetime.now()
    source_weights = {
        "arxiv-cs-ai": 0.9,
        "hackernews": 0.7,
        "jiqizhixin": 0.6,
        "github-trending": 0.8,
        "reddit-ml": 0.5,
    }

    for art in articles:
        score = 0.5  # baseline

        # Freshness decay
        pub = art.get("published_at", "")
        if pub:
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00").split("+")[0])
                age_hours = max(0, (now - pub_dt).total_seconds() / 3600)
                score += max(0, 1.0 - age_hours / 48) * cfg.ranking.freshness_decay
            except (ValueError, TypeError):
                pass

        # Source reputation weight
        src = art.get("source_id", "")
        score += source_weights.get(src, 0.3) * 0.3

        # Small random jitter for diversity
        score += random.uniform(0, 0.05)

        art["score"] = round(score, 4)

    return sorted(articles, key=lambda a: a.get("score", 0), reverse=True)


def _blend_score(db_conn, articles: list, cfg, blend: float) -> list:
    """Progressive blend between cold-start and interest-driven scoring."""
    articles = _cold_start_score(articles, cfg)

    user_topics = _get_user_topics(db_conn)
    if not user_topics:
        return articles  # no interest data yet, keep cold-start scores

    exploration_count = max(cfg.ranking.exploration_floor, int(len(articles) * 0.2))
    scored = []

    for i, art in enumerate(articles):
        cold_score = art.get("score", 0.5)
        interest_bonus = _calculate_interest_bonus(art, user_topics)
        # Progressive blend: as blend increases, interest signal takes over
        art["score"] = round(cold_score * (1 - blend) + (cold_score + interest_bonus) * blend, 4)
        art["_explore"] = i >= (len(articles) - exploration_count)
        scored.append(art)

    return sorted(scored, key=lambda a: a.get("score", 0), reverse=True)


def _get_user_topics(db_conn) -> set:
    """Extract user interest topics from read_records.topics."""
    rows = db_conn.execute(
        "SELECT DISTINCT topics FROM read_records WHERE topics != '' AND feedback = 'interested'"
    ).fetchall()
    topics = set()
    for (t,) in rows:
        for topic in t.split(","):
            topic = topic.strip()
            if topic:
                topics.add(topic.lower())
    return topics


def _calculate_interest_bonus(art: dict, user_topics: set) -> float:
    """Calculate interest bonus based on article content matching user topics."""
    if not user_topics:
        return 0.0

    title = art.get("title", "").lower()
    summary = art.get("summary", "").lower()
    text = title + " " + summary

    matches = sum(1 for t in user_topics if t in text)
    if matches == 0:
        return 0.0
    return min(0.4, matches * 0.15)
