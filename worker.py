"""웹 API와 분리된 크롤링·정리 스케줄 Worker."""

from __future__ import annotations

import logging
import os
import json
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

logger = logging.getLogger(__name__)


class ResumeAwareScheduler(BlockingScheduler):
    """Recheck wall-clock schedules soon after Windows resumes from sleep."""

    def _process_jobs(self):
        wait_seconds = super()._process_jobs()
        return 30 if wait_seconds is None else min(30, wait_seconds)


def unfinished_collection() -> bool:
    try:
        report = json.loads(Path('data/site_sync_report.json').read_text(encoding='utf-8'))
        return bool(report.get('counts', {}).get('pending') or report.get('pending_index'))
    except (OSError, ValueError):
        return False


def incremental_job() -> None:
    from crawler.site_sync import run_site_sync
    # Finish the initial traversal before resetting thousands of saved URLs.
    resume = unfinished_collection()
    logger.info('공식 사이트 예약 갱신 시작: resume=%s', resume)
    run_site_sync(resume=resume)


def cleanup_job() -> None:
    from main import cleanup_old_conversations_job
    cleanup_old_conversations_job()


def official_sources_job() -> None:
    # Retry/resume the same comprehensive frontier. Evaluation spreadsheets
    # must not be a hidden dependency of production data refresh.
    from crawler.site_sync import run_site_sync
    run_site_sync(resume=True)


def staff_directory_job() -> None:
    from chatbot.dept_directory import refresh_staff_directory
    refresh_staff_directory()


def run_worker() -> None:
    scheduler = ResumeAwareScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        incremental_job,
        trigger="cron",
        hour=int(os.getenv("CRAWL_HOUR", "3")),
        minute=int(os.getenv("CRAWL_MINUTE", "0")),
        id="incremental_crawl",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=21600,
    )
    scheduler.add_job(
        cleanup_job,
        trigger="cron",
        hour=int(os.getenv("CLEANUP_HOUR", "4")),
        minute=int(os.getenv("CLEANUP_MINUTE", "0")),
        id="conversation_ttl_cleanup",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=21600,
    )
    scheduler.add_job(
        official_sources_job, trigger="cron", hour=4, minute=15,
        id="official_sources_refresh", max_instances=1, coalesce=True,
        misfire_grace_time=21600,
    )
    scheduler.add_job(
        staff_directory_job, trigger="cron", hour=4, minute=45,
        id="staff_directory_refresh", max_instances=1, coalesce=True,
        misfire_grace_time=21600,
    )
    logger.info("Worker 시작: 전체 공식 사이트 갱신 %02d:%02d / 재개 04:15 / 직원 안내 04:45 / 정리 04:00",
                int(os.getenv("CRAWL_HOUR", "3")), int(os.getenv("CRAWL_MINUTE", "0")))
    if os.getenv("WORKER_RUN_ON_START", "false").lower() == "true":
        logger.info("WORKER_RUN_ON_START=true: 시작 직후 증분 크롤링 실행")
        scheduler.add_job(incremental_job, id="initial_incremental", max_instances=1)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker 종료")


if __name__ == "__main__":
    run_worker()
