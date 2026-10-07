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


def official_sources_job() -> None:
    from scripts.ingest_official_materials import DEFAULT_DIR, ingest
    workbook = DEFAULT_DIR / "사하구 홈페이지_100개 질문.xlsx"
    if workbook.is_file():
        logger.info("공식 페이지 100건 갱신 시작")
        logger.info("공식 페이지 갱신 결과: %s", ingest(DEFAULT_DIR, reports=False))


def staff_directory_job() -> None:
    from chatbot.dept_directory import refresh_staff_directory
    refresh_staff_directory()


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
    scheduler.add_job(
        official_sources_job, trigger="cron", hour=4, minute=15,
        id="official_sources_refresh", max_instances=1, coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        staff_directory_job, trigger="cron", hour=4, minute=45,
        id="staff_directory_refresh", max_instances=1, coalesce=True,
        misfire_grace_time=3600,
    )
    logger.info("Worker 시작: 증분 크롤링 03:00 / 공식 페이지 04:15 / 직원 안내 04:45 / 정리 04:00")
    if os.getenv("WORKER_RUN_ON_START", "false").lower() == "true":
        logger.info("WORKER_RUN_ON_START=true: 시작 직후 증분 크롤링 실행")
        scheduler.add_job(incremental_job, id="initial_incremental", max_instances=1)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker 종료")


if __name__ == "__main__":
    run_worker()
