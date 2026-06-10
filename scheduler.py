"""APScheduler-based task scheduler for AI News Digest."""
import logging
from datetime import date

logger = logging.getLogger("scheduler")

_scheduler = None


def _weekly_md_job(db_conn, cfg, orchestrator_module):
    """Generate and push weekly Markdown review."""
    import asyncio
    from ai.client import AIClient

    async def _run():
        ai_client = None
        if cfg.deepseek_api_key:
            ai_client = AIClient(cfg.deepseek_api_key)
        if not ai_client:
            logger.warning("Weekly MD: No AI client available")
            return
        result = orchestrator_module.generate_weekly_review(db_conn, ai_client, cfg)
        if result and result.get("status") == "ok":
            pushed = await orchestrator_module.push_weekly_review(db_conn, cfg)
            logger.info(f"Weekly MD: generated and pushed={pushed}")

    asyncio.run(_run())


def _save_graph_snapshot(db_conn, today_str: str):
    """Save concept_nodes + JSON snapshot for today. Called after collection."""
    from db.models import (get_graph_data, save_graph_snapshot,
                           save_concept_nodes, prune_stale_concepts,
                           get_concept_nodes_by_date)
    from web.routes.graph import _build_nodes_and_edges

    rows = get_graph_data(db_conn, "today")
    if not rows:
        logger.info("Scheduler: no concept data, skipping snapshot")
        return

    snap_nodes, snap_edges = _build_nodes_and_edges(rows)

    # Primary: write to concept_nodes (single source of truth)
    save_concept_nodes(db_conn, today_str, snap_nodes)

    # Secondary: generate JSON snapshot from concept_nodes (backup/compat)
    node_records = get_concept_nodes_by_date(db_conn, today_str)
    snapshot_nodes = [
        {"id": n["label"], "label": n["label"], "type": "concept",
         "query_count": int(n["weight"]), "weight": n["weight"]}
        for n in node_records
    ]
    save_graph_snapshot(db_conn, today_str, "today",
                        {"nodes": snapshot_nodes, "edges": snap_edges})

    # Update lifecycle states
    try:
        from ai.lifecycle import update_all_lifecycle_states
        update_all_lifecycle_states(db_conn, today_str)
    except ImportError:
        pass  # lifecycle module not yet created (Task 5)

    # Prune stale concepts
    prune_stale_concepts(db_conn)

    logger.info(f"Scheduler: concept_nodes + snapshot saved for {today_str}")


def create_scheduler(db_conn, cfg, orchestrator_module):
    """Create and configure APScheduler with daily collection job."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    import asyncio

    global _scheduler

    _scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
    _scheduler._db_conn = db_conn
    _scheduler._cfg = cfg
    _scheduler._orchestrator = orchestrator_module

    async def daily_job():
        logger.info("Scheduler: starting daily collection")
        try:
            count = await orchestrator_module.run_full_pipeline(db_conn, None, cfg)
            logger.info(f"Scheduler: daily collection complete — {count} articles")
            # Generate graph snapshot AFTER collection completes
            try:
                today_str = date.today().isoformat()
                _save_graph_snapshot(db_conn, today_str)
            except Exception as e:
                logger.warning(f"Scheduler: graph snapshot failed: {e}")
        except Exception as e:
            logger.error(f"Scheduler: daily job failed: {e}")

    def job_wrapper():
        import asyncio
        asyncio.run(daily_job())

    try:
        _scheduler.add_job(
            job_wrapper,
            CronTrigger.from_crontab(cfg.scheduler.cron, timezone='Asia/Shanghai'),
            id='daily_collection',
            name='Daily collection and push',
            replace_existing=True,
        )
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid scheduler cron '{cfg.scheduler.cron}': {e}. Using default '0 9 * * *'")
        _scheduler.add_job(
            job_wrapper,
            CronTrigger.from_crontab("0 9 * * *", timezone='Asia/Shanghai'),
            id='daily_collection',
            name='Daily collection and push',
            replace_existing=True,
        )

    def weekly_md_wrapper():
        _weekly_md_job(db_conn, cfg, orchestrator_module)

    try:
        _scheduler.add_job(
            weekly_md_wrapper,
            CronTrigger.from_crontab("0 8 * * 1", timezone='Asia/Shanghai'),
            id='weekly_md_review',
            name='Weekly Markdown review generation and push',
            replace_existing=True,
        )
    except Exception as e:
        logger.warning(f"Could not add weekly_md job: {e}")

    return _scheduler


def start_scheduler(db_conn, cfg, orchestrator_module):
    """Start the scheduler and optionally run immediate collection."""
    import asyncio

    sched = create_scheduler(db_conn, cfg, orchestrator_module)
    sched.start()
    logger.info(f"Scheduler started — daily at {cfg.scheduler.cron}")

    if cfg.scheduler.run_on_startup:
        logger.info("Scheduler: run_on_startup enabled, triggering immediate collection")
        try:
            asyncio.run(orchestrator_module.run_full_pipeline(db_conn, None, cfg))
            # v1.0: startup collection also saves to concept_nodes
            today_str = date.today().isoformat()
            _save_graph_snapshot(db_conn, today_str)
        except Exception as e:
            logger.error(f"Scheduler: startup collection failed: {e}")


def stop_scheduler():
    """Shut down the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
