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
    from web.app import create_app, set_globals
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
    from db.models import (
        insert_article, has_digest_today, create_digest, mark_webhook_sent, cleanup_old_data
    )
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
                             language=art.language)
        if aid:
            new_articles.append({
                "id": aid, "title": art.title, "summary": art.summary,
                "source_id": art.source_id, "language": art.language,
                "published_at": art.published_at,
            })

    logger.info(f"New articles: {len(new_articles)}")
    if not new_articles:
        return

    deduped = filter_duplicates_by_title(new_articles, threshold=0.85)
    clusters = cluster_articles(deduped, threshold=cfg.cluster_threshold)

    import random
    today_str = datetime.now().strftime("%Y-%m-%d")
    for i, cluster in enumerate(clusters):
        label = make_cluster_label(cluster)
        cid = make_cluster_id(today_str, i)

        if ai_client and cluster:
            try:
                titles = "\n".join([a.get("title", "")[:80] for a in cluster[:5]])
                sys_p = "你是一个信息分类助手。"
                usr_p = f"为以下一组相关文章生成一个简短的中文标签（不超过15个字）：\n\n{titles}\n\n标签："
                label, _ = ai_client.chat(sys_p, usr_p, max_tokens=30)
                label = label.strip().strip('"').strip("'")
            except Exception:
                pass

        db_conn.execute(
            "INSERT INTO clusters (id, label, digest_date) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET label = ?",
            (cid, label, today_str, label)
        )
        for art in cluster:
            db_conn.execute(
                "INSERT OR IGNORE INTO cluster_articles (cluster_id, article_id) VALUES (?, ?)",
                (cid, art["id"])
            )
    db_conn.commit()

    small_clusters = [c for c in clusters if len(c) <= 2]
    if small_clusters:
        explore_count = max(1, int(len(new_articles) * cfg.exploration_rate))
        explore_articles = []
        for c in small_clusters:
            explore_articles.extend(c)
        random.shuffle(explore_articles)
        explore_articles = explore_articles[:explore_count]
        for art in explore_articles:
            db_conn.execute(
                "UPDATE articles SET summary = '[探索] ' || COALESCE(summary, '') WHERE id = ?",
                (art["id"],)
            )
        db_conn.commit()

    if not has_digest_today(db_conn):
        all_ids = [a["id"] for cluster in clusters for a in cluster]
        all_ids = all_ids[:cfg.max_daily_articles]
        create_digest(db_conn, all_ids)

        cluster_data = []
        seen_ids = set()
        for cluster in clusters:
            arts = [a for a in cluster if a["id"] in all_ids and a["id"] not in seen_ids]
            if arts:
                for a in arts:
                    seen_ids.add(a["id"])
                cluster_data.append({"label": make_cluster_label(cluster), "articles": arts})

        success = await send_wecom_digest(
            cfg.wecom_webhook_url, today_str,
            len(all_articles), len(all_ids), cluster_data
        )
        if success:
            mark_webhook_sent(db_conn)
            logger.info("WeChat push sent successfully")

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
        target=start_server, args=(db_conn, ai_client, cfg, port), daemon=True
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
