"""웹 API와 분리된 크롤링·정리 스케줄 Worker."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

logger = logging.getLogger(__name__)


def incremental_job() -> dict:
    from main import run_incremental
    return run_incremental()


def cleanup_job() -> None:
    from main import cleanup_old_conversations_job
    cleanup_old_conversations_job()


def official_sources_job() -> dict:
    from scripts.ingest_official_materials import DEFAULT_DIR, ingest
    logger.info("질문 목록·우선 서비스의 공식 페이지 갱신 시작")
    result = ingest(DEFAULT_DIR, reports=False)
    logger.info("공식 페이지 갱신 결과: %s", result)
    return result


def staff_directory_job() -> dict:
    from chatbot.dept_directory import refresh_staff_directory
    data = refresh_staff_directory()
    return {'staff_rows': len(data.get('rows') or []), 'checked_at': data.get('generated_at')}


def refresh_coordinator():
    from worker_recovery import RefreshCoordinator, RefreshTask
    # Small, important official snapshots recover before a broad crawl.
    return RefreshCoordinator([
        RefreshTask('staff_directory_refresh', staff_directory_job),
        RefreshTask('official_sources_refresh', official_sources_job),
        RefreshTask('conversation_ttl_cleanup', cleanup_job),
        RefreshTask('incremental_crawl', incremental_job),
    ], Path(__file__).resolve().parent / '.local' / 'worker_refresh_state.json')


def run_worker() -> None:
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    recovery = refresh_coordinator()
    scheduler.add_job(
        recovery.run, args=['incremental_crawl'], kwargs={'force': True},
        trigger="cron",
        hour=int(os.getenv("CRAWL_HOUR", "3")),
        minute=int(os.getenv("CRAWL_MINUTE", "0")),
        id="incremental_crawl",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        recovery.run, args=['conversation_ttl_cleanup'], kwargs={'force': True},
        trigger="cron",
        hour=int(os.getenv("CLEANUP_HOUR", "4")),
        minute=int(os.getenv("CLEANUP_MINUTE", "0")),
        id="conversation_ttl_cleanup",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        recovery.run, args=['official_sources_refresh'], kwargs={'force': True}, trigger="cron", hour=4, minute=15,
        id="official_sources_refresh", max_instances=1, coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        recovery.run, args=['staff_directory_refresh'], kwargs={'force': True}, trigger="cron", hour=4, minute=45,
        id="staff_directory_refresh", max_instances=1, coalesce=True,
        misfire_grace_time=3600,
    )
    logger.info("Worker 시작: 증분 크롤링 03:00 / 공식 페이지 04:15 / 직원 안내 04:45 / 정리 04:00")
    scheduler.add_job(recovery.check_overdue, trigger='interval', minutes=5,
        id='overdue_refresh_check', max_instances=1, coalesce=True, misfire_grace_time=None)
    scheduler.add_job(recovery.check_overdue, id='initial_overdue_check', max_instances=1)
    if os.getenv("WORKER_RUN_ON_START", "false").lower() == "true":
        logger.info("WORKER_RUN_ON_START=true: 시작 직후 증분 크롤링 실행")
        scheduler.add_job(recovery.run, args=['incremental_crawl'], kwargs={'force': True},
            id="initial_incremental", max_instances=1)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker 종료")


if __name__ == "__main__":
    run_worker()
