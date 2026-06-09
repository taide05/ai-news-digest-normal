import sys
import os
import asyncio
import logging
import webbrowser
import threading
import time
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")


def check_existing_server(port: int) -> bool:
    import httpx
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=3)
        return resp.headers.get("x-server") == "ai-news-digest"
    except Exception:
        return False


def start_server(db_conn, ai_client, cfg, port: int):
    from web.app import create_app
    from web.globals import set_globals
    import uvicorn

    set_globals(db_conn, ai_client, cfg)
    app = create_app()

    # Add API router after app creation
    from web.routes import api
    app.include_router(api.router)

    config = uvicorn.Config(app, host=cfg.host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


async def run_collection_pipeline(db_conn, ai_client, cfg):
    from collectors.registry import get_all
    from pipeline.dedup import filter_duplicates_by_title
    from pipeline.cluster import cluster_articles, make_cluster_id, make_cluster_label
    from ai.analysis import build_cluster_label_prompt
    from db.models import (
        insert_article, has_digest_today, create_digest, mark_webhook_sent, cleanup_old_data,
        get_weekly_review,
    )
    from db.digest import insert_cluster, insert_cluster_article, mark_article_exploration
    from push import send_wecom_digest

    since = datetime.now() - timedelta(days=2)

    all_articles = []
    collectors = get_all()
    tasks = [c.fetch(since) for c in collectors]
    results = await asyncio.gather(*tasks, return_exceptions=True)

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
    if not new_articles:
        return

    deduped = filter_duplicates_by_title(new_articles, threshold=0.85)
    clusters = cluster_articles(deduped, threshold=cfg.cluster_threshold)

    today_str = datetime.now().strftime("%Y-%m-%d")
    ai_labels = {}
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

        ai_labels[i] = label
        insert_cluster(db_conn, cid, label, today_str)
        for art in cluster:
            insert_cluster_article(db_conn, cid, art["id"])
    db_conn.commit()

    # Smart exploration
    if ai_client:
        small_clusters = [c for c in clusters if len(c) <= 2]
        if small_clusters:
            from ai.analysis import build_exploration_prompt
            from db.models import get_concepts_list
            concepts = [c["term"] for c in get_concepts_list(db_conn)]
            for c in small_clusters:
                for art in c[:1]:  # check first article per cluster
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

    if not has_digest_today(db_conn):
        all_ids = [a["id"] for cluster in clusters for a in cluster]
        all_ids = all_ids[:cfg.max_daily_articles]
        create_digest(db_conn, all_ids)

        cluster_data = []
        seen_ids = set()
        for i, cluster in enumerate(clusters):
            arts = [a for a in cluster if a["id"] in all_ids and a["id"] not in seen_ids]
            if arts:
                for a in arts:
                    seen_ids.add(a["id"])
                cluster_data.append({"label": ai_labels.get(i, make_cluster_label(cluster)), "articles": arts})

        success = await send_wecom_digest(
            cfg.wecom_webhook_url, today_str,
            len(all_articles), len(all_ids), cluster_data
        )
        if success:
            mark_webhook_sent(db_conn)
            logger.info("WeChat push sent successfully")

        # Telegram push
        if cfg.telegram_bot_token and cfg.telegram_chat_id:
            from push_telegram import send_telegram_digest as tg_digest
            success_tg = await tg_digest(
                cfg.telegram_bot_token, cfg.telegram_chat_id,
                today_str, len(all_articles), len(all_ids), cluster_data
            )
            if success_tg:
                logger.info("Telegram push sent successfully")

    # Weekly review auto-push on Mondays
    if datetime.now().weekday() == 0:
        from push import send_wecom_review
        review_week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        review_week_end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        existing = get_weekly_review(db_conn, review_week_start)
        if existing and not existing.get("review_pushed"):
            success = await send_wecom_review(
                cfg.wecom_webhook_url, review_week_start, review_week_end, existing["content"]
            )
            if success:
                db_conn.execute(
                    "UPDATE weekly_reviews SET review_pushed = 1 WHERE week_start = ?",
                    (review_week_start,)
                )
                db_conn.commit()
                logger.info("Weekly review pushed successfully")

            # Telegram weekly review push
            if cfg.telegram_bot_token and cfg.telegram_chat_id:
                from push_telegram import send_telegram_review as tg_review
                await tg_review(
                    cfg.telegram_bot_token, cfg.telegram_chat_id,
                    review_week_start, review_week_end, existing["content"]
                )

    cleanup_old_data(db_conn, cfg.full_text_retention_days, cfg.analysis_cache_retention_days)
    return len(new_articles)


def main():
    from config import load_config
    cfg = load_config()

    port = cfg.port
    for offset in range(3):
        if not check_existing_server(port + offset) or offset == 0:
            port = port + offset
            break

    if check_existing_server(port):
        logger.info(f"Server already running on port {port}, triggering collection")
        webbrowser.open(f"http://127.0.0.1:{port}")
        try:
            import httpx
            httpx.post(f"http://127.0.0.1:{port}/api/collect", timeout=5)
        except Exception:
            pass
        return

    assert cfg.host == "127.0.0.1", "Server must bind to 127.0.0.1 only"

    from db.schema import init_db
    db_path = os.path.join(os.path.dirname(__file__), "ai_news.db")
    db_conn = init_db(db_path)

    ai_client = None
    if cfg.deepseek_api_key:
        from ai.client import AIClient
        ai_client = AIClient(cfg.deepseek_api_key)
    else:
        logger.warning(".env 未找到或未配置 DEEPSEEK_API_KEY，AI 功能不可用")

    server_thread = threading.Thread(
        target=start_server, args=(db_conn, ai_client, cfg, port), daemon=False
    )
    server_thread.start()
    time.sleep(1)

    try:
        count = asyncio.run(run_collection_pipeline(db_conn, ai_client, cfg))
        logger.info(f"Collection complete: {count} new articles")
    except Exception as e:
        logger.error(f"Collection pipeline error: {e}")

    webbrowser.open(f"http://127.0.0.1:{port}")

    try:
        while server_thread.is_alive():
            server_thread.join(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")

    db_conn.close()


if __name__ == "__main__":
    main()
