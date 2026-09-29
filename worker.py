"""웹 API와 분리된 크롤링·정리 스케줄 Worker."""

from __future__ import annotations

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler

logger = logging.getLogger(__name__)


def incremental_job() -> None:
    from main import run_incremental
    run_incremental()


def cleanup_job() -> None:
    from main import cleanup_old_conversations_job
    cleanup_old_conversations_job()


def run_worker() -> None:
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        incremental_job,
        trigger="cron",
        hour=int(os.getenv("CRAWL_HOUR", "3")),
        minute=int(os.getenv("CRAWL_MINUTE", "0")),
        id="incremental_crawl",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        cleanup_job,
        trigger="cron",
        hour=int(os.getenv("CLEANUP_HOUR", "4")),
        minute=int(os.getenv("CLEANUP_MINUTE", "0")),
        id="conversation_ttl_cleanup",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    logger.info("Worker 시작: 증분 크롤링 03:00 / 정리 작업 04:00")
    if os.getenv("WORKER_RUN_ON_START", "false").lower() == "true":
        logger.info("WORKER_RUN_ON_START=true: 시작 직후 증분 크롤링 실행")
        scheduler.add_job(incremental_job, id="initial_incremental", max_instances=1)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker 종료")


if __name__ == "__main__":
    run_worker()
