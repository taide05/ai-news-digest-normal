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
    import orchestrator as orch
    count = await orch.run_full_pipeline(db_conn, ai_client, cfg)

    # Weekly review auto-push on Mondays (after pipeline completes)
    if datetime.now().weekday() == 0:
        try:
            import orchestrator as orch
            result = orch.generate_weekly_review(db_conn, ai_client, cfg)
            if result and result.get("status") == "ok":
                await orch.push_weekly_review(db_conn, cfg)
        except Exception as e:
            logger.error(f"Weekly review error: {e}")

    return count


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
