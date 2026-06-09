"""Tests for scheduler.py — APScheduler integration."""
import pytest


def test_create_scheduler_returns_scheduler(test_db, test_config):
    """create_scheduler() returns a BackgroundScheduler with at least 1 job."""
    from scheduler import create_scheduler
    import orchestrator as orch
    test_config.scheduler.enabled = True
    sched = create_scheduler(test_db, test_config, orch)
    assert sched is not None
    assert not sched.running  # not started yet (create only)
    # Should have at least 1 job
    jobs = sched.get_jobs()
    assert len(jobs) >= 1
    job_ids = [j.id for j in jobs]
    assert 'daily_collection' in job_ids


def test_scheduler_start_stop(test_db, test_config):
    """start() then stop_scheduler() shuts down cleanly."""
    from scheduler import create_scheduler, stop_scheduler
    import orchestrator as orch
    sched = create_scheduler(test_db, test_config, orch)
    sched.start()
    assert sched.running
    stop_scheduler()
    # After shutdown, scheduler should not be running


def test_start_scheduler_without_startup_run(test_db, test_config):
    """start_scheduler() with run_on_startup=False starts scheduler but does not
    trigger immediate collection."""
    from scheduler import start_scheduler, stop_scheduler
    import orchestrator as orch
    test_config.scheduler.enabled = True
    test_config.scheduler.run_on_startup = False
    try:
        start_scheduler(test_db, test_config, orch)
        from scheduler import _scheduler
        assert _scheduler is not None
        assert _scheduler.running
    finally:
        stop_scheduler()
