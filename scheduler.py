"""APScheduler-based task scheduler for AI News Digest."""
import logging
from datetime import datetime

logger = logging.getLogger("scheduler")

_scheduler = None


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

            # Event-driven Monday review: trigger AFTER collection completes
            if datetime.now().weekday() == 0:
                logger.info("Scheduler: Monday detected, triggering weekly review")
                from ai.client import AIClient
                ai_client = None
                if cfg.deepseek_api_key:
                    ai_client = AIClient(cfg.deepseek_api_key)
                if ai_client:
                    result = orchestrator_module.generate_weekly_review(db_conn, ai_client, cfg)
                    if result and result.get("status") == "ok":
                        await orchestrator_module.push_weekly_review(db_conn, cfg)
        except Exception as e:
            logger.error(f"Scheduler: daily job failed: {e}")

    def job_wrapper():
        import asyncio
        asyncio.run(daily_job())

    _scheduler.add_job(
        job_wrapper,
        CronTrigger.from_crontab(cfg.scheduler.cron, timezone='Asia/Shanghai'),
        id='daily_collection',
        name='Daily collection and push',
        replace_existing=True,
    )

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
        except Exception as e:
            logger.error(f"Scheduler: startup collection failed: {e}")


def stop_scheduler():
    """Shut down the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
