"""Pipeline orchestrator -- composable stage functions for collection pipeline."""
import logging
import asyncio
from datetime import datetime, timedelta

logger = logging.getLogger("orchestrator")


# Stage 1: Collect
async def collect_all(db_conn, cfg) -> list:
    """Fetch from all collectors, insert articles, return new_articles list."""
    from collectors.registry import get_all
    from db.models import insert_article

    since = datetime.now() - timedelta(days=2)
    collectors = get_all()
    tasks = [c.fetch(since) for c in collectors]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Collector {collectors[i].name} failed: {result}")
        else:
            all_articles.extend(result)
            logger.info(f"Collector {collectors[i].name}: {len(result)} articles")

    logger.info(f"Total fetched: {len(all_articles)}")

    new_articles = []
    for art in all_articles:
        aid = insert_article(db_conn, art.source_id, art.url, art.title,
                             summary=art.summary, content=art.content or "",
                             author=art.author, published_at=art.published_at,
                             language=art.language, commit=False)
        if aid:
            new_articles.append({
                "id": aid, "title": art.title, "summary": art.summary,
                "url": art.url, "source_id": art.source_id, "language": art.language,
                "published_at": art.published_at,
            })
    db_conn.commit()
    logger.info(f"New articles: {len(new_articles)}")
    return new_articles


# Stage 2: Dedup
def dedup_articles(db_conn, articles: list) -> list:
    from pipeline.dedup import filter_duplicates_by_title
    return filter_duplicates_by_title(articles, threshold=0.85)


# Stage 3: Rank
def rank_articles(db_conn, articles: list, cfg) -> list:
    """Score articles using dual-phase strategy."""
    from pipeline.ranking import score_articles
    return score_articles(db_conn, articles, cfg)


# Stage 4: Cluster
def cluster_articles(db_conn, articles: list, cfg) -> list:
    from pipeline.cluster import cluster_articles as do_cluster
    return do_cluster(articles, threshold=cfg.cluster_threshold)


# Stage 5: Annotate (labels + exploration only, no deep analysis)
def annotate_clusters(db_conn, ai_client, clusters: list, cfg) -> dict:
    from ai.analysis import build_cluster_label_prompt, build_exploration_prompt
    from db.digest import insert_cluster, insert_cluster_article, mark_article_exploration
    from pipeline.cluster import make_cluster_id, make_cluster_label
    from db.models import get_concepts_list

    today_str = datetime.now().strftime("%Y-%m-%d")
    labels = {}

    for i, cluster in enumerate(clusters):
        label = make_cluster_label(cluster)
        cid = make_cluster_id(today_str, i)

        if ai_client and cluster:
            try:
                titles = "\n".join([a.get("title", "")[:80] for a in cluster[:5]])
                sys_p, usr_p = build_cluster_label_prompt(titles)
                label, _ = ai_client.chat(sys_p, usr_p, max_tokens=30)
                label = label.strip().strip('"').strip("'")
            except Exception as e:
                logger.warning(f"AI label generation failed: {e}")

        labels[i] = label
        insert_cluster(db_conn, cid, label, today_str)
        for art in cluster:
            insert_cluster_article(db_conn, cid, art["id"])
    db_conn.commit()

    # Smart exploration
    if ai_client:
        small_clusters = [c for c in clusters if len(c) <= 2]
        if small_clusters:
            concepts = [c["term"] for c in get_concepts_list(db_conn)]
            for c in small_clusters:
                for art in c[:1]:
                    try:
                        sys_p, usr_p = build_exploration_prompt(
                            art.get("title", ""), art.get("summary", "") or "", concepts
                        )
                        answer, _ = ai_client.chat(sys_p, usr_p, max_tokens=5)
                        if "是" in answer:
                            mark_article_exploration(db_conn, art["id"])
                    except Exception as e:
                        logger.warning(f"Exploration check failed: {e}")
            db_conn.commit()

    return labels


# Stage 6: Discover sources (placeholder until Task 6)
async def discover_sources(db_conn, ai_client, clusters: list, cfg) -> list:
    """Discover new sources from articles. Placeholder until Task 6."""
    return []


# Stage 7: Push
async def push_to_channels(db_conn, cfg, clusters: list, labels: dict, total_fetched: int) -> bool:
    """Push digest through all configured channels."""
    from db.models import has_digest_today, create_digest, mark_webhook_sent

    if has_digest_today(db_conn):
        return False

    all_ids = [a["id"] for cluster in clusters for a in cluster]
    all_ids = all_ids[:cfg.max_daily_articles]
    create_digest(db_conn, all_ids)

    today_str = datetime.now().strftime("%Y-%m-%d")
    cluster_data = []
    seen_ids = set()
    for i, cluster in enumerate(clusters):
        arts = [a for a in cluster if a["id"] in all_ids and a["id"] not in seen_ids]
        if arts:
            for a in arts:
                seen_ids.add(a["id"])
            from pipeline.cluster import make_cluster_label
            cluster_data.append({
                "label": labels.get(i, make_cluster_label(cluster)),
                "articles": arts,
            })

    # Use existing push functions until Task 3 refactors them
    success = False
    if cfg.wecom_webhook_url:
        from push import send_wecom_digest
        ok = await send_wecom_digest(cfg.wecom_webhook_url, today_str, total_fetched, len(all_ids), cluster_data)
        if ok:
            success = True
            logger.info("WeChat push sent successfully")

    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        from push_telegram import send_telegram_digest
        ok = await send_telegram_digest(cfg.telegram_bot_token, cfg.telegram_chat_id, today_str, total_fetched, len(all_ids), cluster_data)
        if ok:
            success = True
            logger.info("Telegram push sent successfully")

    if success:
        mark_webhook_sent(db_conn)
    return success


# Full pipeline
async def run_full_pipeline(db_conn, ai_client, cfg):
    """Run the complete collection pipeline. Returns count of new articles."""
    articles = await collect_all(db_conn, cfg)
    if not articles:
        return 0

    deduped = dedup_articles(db_conn, articles)
    ranked = rank_articles(db_conn, deduped, cfg)
    clusters = cluster_articles(db_conn, ranked, cfg)
    labels = annotate_clusters(db_conn, ai_client, clusters, cfg)

    await push_to_channels(db_conn, cfg, clusters, labels, len(articles))
    await discover_sources(db_conn, ai_client, clusters, cfg)

    from db.maintenance import cleanup_old_data
    cleanup_old_data(db_conn, cfg.full_text_retention_days, cfg.analysis_cache_retention_days)

    return len(articles)


# Weekly review
def generate_weekly_review(db_conn, ai_client, cfg):
    """Generate weekly review. Returns dict or None."""
    from db.models import get_concepts_list
    from db.queries import get_read_articles_with_insights, get_read_article_ids_since, get_feedback_articles
    from db.queries import get_weekly_review, save_weekly_review
    from ai.analysis import build_review_prompt
    from utils import get_week_bounds

    week_start, week_end = get_week_bounds()
    existing = get_weekly_review(db_conn, week_start)
    if existing:
        return {"status": "exists", "review": existing}

    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    articles = get_read_articles_with_insights(db_conn, since)
    concepts = [c["term"] for c in get_concepts_list(db_conn)]
    interested = get_feedback_articles(db_conn, since, "interested")
    not_interested = get_feedback_articles(db_conn, since, "not_interested")

    if not articles:
        return None

    if not ai_client:
        return None

    system, user = build_review_prompt(articles, concepts, interested, not_interested)
    content, tokens = ai_client.chat(system, user, max_tokens=2048)
    article_ids = get_read_article_ids_since(db_conn, since)
    save_weekly_review(db_conn, week_start, week_end, content, article_ids)

    return {"status": "ok", "content": content, "week_start": week_start, "week_end": week_end}


async def push_weekly_review(db_conn, cfg) -> bool:
    """Push weekly review through configured channels."""
    from db.queries import get_weekly_review
    from utils import get_week_bounds

    week_start, week_end = get_week_bounds()
    review = get_weekly_review(db_conn, week_start)
    if not review or review.get("review_pushed"):
        return False

    success = False
    if cfg.wecom_webhook_url:
        from push import send_wecom_review
        ok = await send_wecom_review(cfg.wecom_webhook_url, week_start, week_end, review["content"])
        if ok:
            success = True

    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        from push_telegram import send_telegram_review
        ok = await send_telegram_review(cfg.telegram_bot_token, cfg.telegram_chat_id, week_start, week_end, review["content"])
        if ok:
            success = True

    if success:
        db_conn.execute(
            "UPDATE weekly_reviews SET review_pushed = 1 WHERE week_start = ?",
            (week_start,)
        )
        db_conn.commit()
    return success
