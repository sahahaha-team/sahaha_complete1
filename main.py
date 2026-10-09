"""
사하구청 AI 상담사 - 데이터 파이프라인 + 웹 서버
실행:
  python main.py --mode web          # 웹 서버 실행
  python main.py --mode crawl        # 전수 크롤링
  python main.py --mode incremental  # 증분 크롤링
  python main.py --mode process      # 정제 + 태깅
  python main.py --mode embed        # 벡터 임베딩
  python main.py --mode all          # 전체 파이프라인
  python main.py --mode stats        # 통계 확인
  python main.py --mode ingest-files # PDF/HWPX/HWP 매뉴얼 적재 (--path 폴더/파일)
"""

import os
import argparse
import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from tqdm import tqdm

os.makedirs("data", exist_ok=True)

from config import TARGET_MENUS, MAX_PAGES_PER_MENU, BASE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/pipeline.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)


def run_crawl(menu_filter: str = None):
    """1단계: 전수 크롤링 → MySQL 저장"""
    from crawler.saha_crawler import SahaCrawler
    from database_db.database import Database

    crawler = SahaCrawler(use_selenium=False)
    db = Database()

    menus = {k: v for k, v in TARGET_MENUS.items() if menu_filter is None or k == menu_filter}

    total_saved = 0
    try:
        for menu_name, menu_path in menus.items():
            start_url = BASE_URL + menu_path
            pages = crawler.crawl_menu(menu_name, start_url, max_pages=MAX_PAGES_PER_MENU)

            saved = 0
            for page in pages:
                if db.save_raw_page(page):
                    saved += 1

            logger.info(f"[{menu_name}] {saved}/{len(pages)}개 신규 저장")
            total_saved += saved
    finally:
        crawler.close()

    logger.info(f"크롤링 완료. 총 {total_saved}개 신규 페이지 저장")
    return total_saved


def _rebuild_bm25_index():
    """
    증분 변경 후 BM25 싱글턴 인덱스를 재구축.
    벡터 검색은 Supabase 서버사이드라 즉시 최신 상태이지만, BM25는
    웹 프로세스 메모리의 싱글턴이므로 명시적으로 다시 빌드해야
    증분 변경(신규/수정/삭제)이 키워드 검색에도 반영된다.
    """
    try:
        from chatbot.bm25_index import BM25Index
        BM25Index().rebuild()
        logger.info("BM25 인덱스 재구축 완료 (증분 변경 반영)")
    except Exception as e:
        logger.warning(f"BM25 인덱스 재구축 실패 (서버 재시작 시 반영): {e}")


def run_incremental(menu_filter: str = None):
    """
    증분 크롤링: ETag/Last-Modified 기반 조건부 GET으로 변경분만 다운로드.

    동작:
      1. DB에서 (url, etag, last_modified, category)를 읽어 크롤러에 주입
      2. BFS 큐를 (menu landing + 해당 카테고리의 known URL)로 시드 → landing이
         304이어도 알려진 URL은 모두 점검
      3. fetch_page가 If-None-Match / If-Modified-Since 헤더로 요청
         - 304: 본문 다운로드 없음 (가장 흔한 경로 = 서버 부하 최소화)
         - 200: 파싱 후 content_hash로 한 번 더 비교 (서버가 검증자를 안 줄 때 대비)
         - 404: 페이지 삭제 — DB에서도 제거
         - 일시 실패: 보존
      4. 변경된 페이지만 청크 재처리·재임베딩, BM25 인덱스 재구축
    """
    from crawler.saha_crawler import SahaCrawler
    from database_db.database import Database

    crawler = SahaCrawler(use_selenium=False)
    db = Database()

    menus = {k: v for k, v in TARGET_MENUS.items() if menu_filter is None or k == menu_filter}

    # 1. 캐시 검증자 + 메뉴별 known URL 준비
    # Local reports share administrative categories with web pages, but they
    # must never enter the HTTP crawl or its orphan deletion scope.
    from chatbot.evidence import is_official_document
    validators = {url: value for url, value in db.get_cache_validators().items()
                  if is_official_document({"metadata": {"url": url}})}
    crawler.set_cache_validators({
        u: {"etag": v.get("etag"), "last_modified": v.get("last_modified")}
        for u, v in validators.items()
    })
    known_by_menu: dict[str, list[str]] = {m: [] for m in menus}
    for u, v in validators.items():
        cat = v.get("category")
        if cat in known_by_menu:
            known_by_menu[cat].append(u)

    stats = {"new": 0, "updated": 0, "unchanged": 0, "deleted": 0}
    changed_urls: list[str] = []
    queued_job_urls: list[str] = []
    seen_urls: set[str] = set()
    started_at = datetime.now(timezone.utc)
    run_id = db.start_crawl_run(mode="incremental", menu=menu_filter)
    run_status = "succeeded"
    run_error = None

    try:
        for menu_name, menu_path in menus.items():
            start_url = BASE_URL + menu_path
            pages = crawler.crawl_menu(
                menu_name, start_url,
                max_pages=MAX_PAGES_PER_MENU,
                known_urls=known_by_menu.get(menu_name, []),
                exclude_urls=seen_urls,
            )

            for page in pages:
                seen_urls.add(page.url)

                if page.transient_fail:
                    # 일시 실패는 무시 — 다음 회차 재시도. 삭제로 오판하지 않도록 seen에는 포함.
                    continue

                if page.deleted:
                    db.delete_page(page.url)
                    stats["deleted"] += 1
                    logger.info(f"  [DELETED-404] {page.url}")
                    continue

                if page.not_modified:
                    stats["unchanged"] += 1
                    db.mark_page_checked(page.url)
                    continue

                # 정상 응답 — content_hash로 한 번 더 비교 (서버가 검증자를 안 줘서
                # 200이 와도 본문은 동일할 수 있음)
                result = db.upsert_raw_page(page)
                stats[result] += 1
                db.mark_page_checked(page.url)
                if result in ("new", "updated"):
                    changed_urls.append(page.url)
                    if db.enqueue_ingestion_job(page.url, page.category) is not None:
                        queued_job_urls.append(page.url)
                    logger.info(f"  [{result.upper()}] {page.title[:40]} - {page.url}")

        # 2. 사라진 페이지 정리: known URL 중 이번 회차에 한 번도 방문되지 않은 것
        scoped_known_urls = {
            url for url, validator in validators.items()
            if validator.get("category") in menus
        }
        orphans = scoped_known_urls - seen_urls
        for url in orphans:
            db.delete_page(url)
            stats["deleted"] += 1
            logger.info(f"  [DELETED-orphan] {url}")

        logger.info(
            f"증분 크롤링 완료 - "
            f"신규: {stats['new']}개 / 변경: {stats['updated']}개 / "
            f"삭제: {stats['deleted']}개 / 변경없음: {stats['unchanged']}개"
        )

        # 4. 변경된 페이지만 재처리 (신규/수정)
        if changed_urls:
            db.update_ingestion_jobs(queued_job_urls, "running")
            from processor.data_cleaner import DataCleaner
            from processor.metadata_tagger import MetadataTagger
            from database_db.vector_store import VectorStore

            # 변경 URL은 같은 URL/인덱스의 chunk_id를 재사용하므로 기존 ID를
            # 중복으로 건너뛰지 않고 새 본문 전체를 다시 만든다.
            cleaner = DataCleaner()
            tagger = MetadataTagger()
            vs = VectorStore()
            logger.info(f"변경된 {len(changed_urls)}개 페이지 재처리 시작...")
            changed_pages = db.get_pages_by_urls(changed_urls)

            all_tagged = []
            for raw in tqdm(changed_pages, desc="재처리 중"):
                class _P:
                    url = raw.url
                    title = raw.title
                    content = raw.content
                    category = raw.category
                    sub_category = raw.sub_category
                    attachments = getattr(raw, "attachments", None) or []

                chunks = cleaner.process(_P())
                if not chunks:
                    continue
                tagged = tagger.tag_batch(chunks)
                all_tagged.extend(tagged)

            if all_tagged:
                db.save_chunks_bulk(all_tagged)

                new_chunk_pairs = []
                for chunk, metadata in all_tagged:
                    class _C:
                        chunk_id = chunk.chunk_id
                        content = chunk.content
                    meta = {
                        "url": chunk.url,
                        "title": chunk.title,
                        "category": chunk.category,
                        "sub_category": chunk.sub_category,
                        "service_type": metadata.get("service_type", "기타"),
                        "department": metadata.get("department") or "",
                        "keywords": json.dumps(metadata.get("keywords", []), ensure_ascii=False),
                        "summary": metadata.get("summary", ""),
                        "attachments": getattr(chunk, "attachments", None) or [],
                    }
                    new_chunk_pairs.append((_C(), meta))

                vs.add_chunks_batch(new_chunk_pairs, batch_size=50, db=db)
                logger.info(f"재처리 완료: {len(all_tagged)}개 청크 업데이트")
            valid_chunk_ids_by_url = {url: set() for url in changed_urls}
            for chunk, _metadata in all_tagged:
                valid_chunk_ids_by_url.setdefault(chunk.url, set()).add(chunk.chunk_id)
            db.delete_stale_derived_for_urls(valid_chunk_ids_by_url)
            db.update_ingestion_jobs(queued_job_urls, "succeeded")
        else:
            logger.info("신규/변경 페이지 없음. 재처리 불필요.")

        # 5. BM25 인덱스 갱신: 신규/수정/삭제가 하나라도 있으면 재구축.
        #    (삭제만 발생한 경우에도 BM25에서 해당 문서를 제거해야 하므로 포함)
        if stats["new"] or stats["updated"] or stats["deleted"]:
            _rebuild_bm25_index()

    except BaseException as exc:
        run_status = "failed"
        run_error = str(exc)
        db.update_ingestion_jobs(queued_job_urls, "failed", run_error)
        raise
    finally:
        crawler.close()
        finished_at = datetime.now(timezone.utc)
        db.finish_crawl_run(run_id, run_status, stats, run_error)
        audit_record = {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "mode": "incremental",
            "menu": menu_filter,
            "status": run_status,
            **stats,
            "error": run_error,
        }
        audit_path = Path("data/crawl_runs.jsonl")
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(audit_record, ensure_ascii=False) + "\n")

    return stats


def run_ingest_files(path: str = None):
    """
    파일 단위 적재: PDF/HWPX/HWP에서 텍스트를 추출해 웹 크롤링과 동일한
    파이프라인(정제 → 태깅 → 청크 저장 → 임베딩 → BM25 재구축)에 태운다.

    크롤러의 PageData 대신 file_loader.FilePageData를 쓰지만 필드가 호환되므로
    upsert_raw_page / DataCleaner / MetadataTagger / VectorStore 모두 그대로 동작한다.
    중복/변경 판정은 기존과 동일하게 content_hash + chunk_id(MD5) 기반 upsert로 처리.
    """
    import json
    from crawler.file_loader import load_files
    from database_db.database import Database
    from processor.data_cleaner import DataCleaner
    from processor.metadata_tagger import MetadataTagger
    from database_db.vector_store import VectorStore
    from config import FILE_INGEST_DIR, FILE_INGEST_CATEGORY

    target = path or FILE_INGEST_DIR
    pages = load_files(target, FILE_INGEST_CATEGORY)
    if not pages:
        logger.info("적재할 파일이 없습니다: %s", target)
        return 0

    db = Database()
    # 변경 파일은 기존 chunk_id와 같아도 내용을 다시 생성해야 한다.
    cleaner = DataCleaner()
    tagger = MetadataTagger()
    vs = VectorStore()

    # 1. 원본 페이지 upsert (신규/변경된 파일만 재처리 대상으로 수집)
    changed = []
    for page in pages:
        result = db.upsert_raw_page(page)
        if result in ("new", "updated"):
            changed.append(page)
            logger.info("  [%s] %s", result.upper(), page.url)

    if not changed:
        logger.info("변경된 파일 없음. 재처리 불필요.")
        return 0

    # 2. 정제 + 태깅
    all_tagged = []
    for page in tqdm(changed, desc="파일 정제·태깅"):
        chunks = cleaner.process(page)
        if not chunks:
            continue
        all_tagged.extend(tagger.tag_batch(chunks))

    if not all_tagged:
        logger.info("생성된 청크 없음.")
        return 0

    # 3. 청크 저장 + 임베딩
    db.save_chunks_bulk(all_tagged)
    chunk_meta_pairs = []
    for chunk, metadata in all_tagged:
        class _C:
            chunk_id = chunk.chunk_id
            content = chunk.content
        chunk_meta_pairs.append((_C(), {
            "url": chunk.url,
            "title": chunk.title,
            "category": chunk.category,
            "sub_category": chunk.sub_category,
            "service_type": metadata.get("service_type", "기타"),
            "department": metadata.get("department") or "",
            "keywords": json.dumps(metadata.get("keywords", []), ensure_ascii=False),
            "summary": metadata.get("summary", ""),
            "attachments": getattr(chunk, "attachments", None) or [],
        }))
    vs.add_chunks_batch(chunk_meta_pairs, batch_size=50, db=db)
    valid_chunk_ids_by_url = {page.url: set() for page in changed}
    for chunk, _metadata in all_tagged:
        valid_chunk_ids_by_url.setdefault(chunk.url, set()).add(chunk.chunk_id)
    db.delete_stale_derived_for_urls(valid_chunk_ids_by_url)

    # 4. BM25 인덱스 재구축 (키워드 검색에도 반영)
    _rebuild_bm25_index()

    logger.info("파일 적재 완료: %d개 파일 → %d개 청크", len(changed), len(all_tagged))
    return len(all_tagged)


def run_process():
    """2단계: 정제 + LLM 태깅 → Supabase chunks 저장"""
    from database_db.database import Database
    from processor.data_cleaner import DataCleaner
    from processor.metadata_tagger import MetadataTagger

    db = Database()
    cleaner = DataCleaner(db=db)
    tagger = MetadataTagger()

    raw_pages = db.get_all_raw_pages()

    logger.info(f"처리 대상: {len(raw_pages)}개 페이지")

    all_tagged = []
    for raw in tqdm(raw_pages, desc="정제 중"):
        class _P:
            url = raw.url
            title = raw.title
            content = raw.content
            category = raw.category
            sub_category = raw.sub_category
            attachments = getattr(raw, "attachments", None) or []

        chunks = cleaner.process(_P())
        if not chunks:
            continue

        tagged = tagger.tag_batch(chunks)
        all_tagged.extend(tagged)

    db.save_chunks_bulk(all_tagged)
    logger.info(f"정제 완료. 총 {len(all_tagged)}개 청크 저장")
    return len(all_tagged)


def run_embed():
    """3단계: 미임베딩 청크 → Supabase 벡터 저장"""
    from database_db.database import Database
    from database_db.vector_store import VectorStore

    db = Database()
    vs = VectorStore()

    chunks = db.get_unembedded_chunks()
    logger.info(f"임베딩 대상: {len(chunks)}개 청크")

    if not chunks:
        logger.info("임베딩할 청크 없음")
        return 0

    import json
    chunk_meta_pairs = []
    for row in chunks:
        class _C:
            chunk_id = row.chunk_id
            content = row.content

        meta = {
            "url": row.url,
            "title": row.title,
            "category": row.category,
            "sub_category": row.sub_category,
            "service_type": row.service_type or "기타",
            "department": getattr(row, "department", None) or "",
            "keywords": row.keywords or "[]",
            "summary": row.summary or "",
            "attachments": getattr(row, "attachments", None) or [],
        }
        chunk_meta_pairs.append((_C(), meta))

    vs.add_chunks_batch(chunk_meta_pairs, batch_size=50, db=db)
    logger.info(f"임베딩 완료. {len(chunk_meta_pairs)}개 벡터 저장")
    return len(chunk_meta_pairs)


def show_stats():
    from database_db.database import Database
    from database_db.vector_store import VectorStore

    db = Database()
    vs = VectorStore()

    db_stats = db.stats()
    vs_stats = vs.collection_stats()

    print("\n===== 파이프라인 현황 =====")
    print(f"  원본 페이지:   {db_stats['raw_pages']}개")
    print(f"  정제 청크:     {db_stats['chunks']}개")
    print(f"  임베딩 완료:   {db_stats['embedded']}개")
    print(f"  벡터 DB:       {vs_stats['total_vectors']}개")
    print(f"  대화 로그:     {db_stats['conversations']}개")
    print("===========================\n")


def cleanup_old_conversations_job():
    """대화 이력 TTL 정리 작업 (스케줄러용)"""
    from database_db.database import Database
    from config import CONVERSATION_TTL_DAYS
    try:
        db = Database(admin=True) if _has_service_key() else Database()
        db.cleanup_old_conversations(ttl_days=CONVERSATION_TTL_DAYS)
    except Exception as e:
        logger.error(f"대화 이력 TTL 정리 실패: {e}")


def _has_service_key() -> bool:
    from config import SUPABASE_SERVICE_KEY
    return bool(SUPABASE_SERVICE_KEY)


def run_web():
    """웹 서버 실행 (FastAPI/uvicorn). 크롤링은 별도 worker 모드에서 실행."""
    from app import run_server
    run_server()


def run_worker():
    """웹 요청과 자원 경쟁이 없도록 별도 스케줄 Worker 실행."""
    from worker import run_worker as start_worker
    start_worker()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="사하구청 AI 상담사")
    parser.add_argument(
        "--mode",
        choices=["crawl", "incremental", "process", "embed", "all", "stats", "web", "worker", "ingest-files", "sync-site"],
        default="web",
        help="실행 모드 (기본: web)",
    )
    parser.add_argument("--menu", type=str, default=None,
                        help=f"특정 메뉴만 크롤링: {list(TARGET_MENUS.keys())}")
    parser.add_argument("--path", type=str, default=None,
                        help="ingest-files 모드에서 적재할 폴더 또는 파일 경로")
    args = parser.parse_args()

    if args.mode == "web":
        run_web()
    elif args.mode == "worker":
        run_worker()
    elif args.mode == "sync-site":
        from crawler.site_sync import run_site_sync
        run_site_sync()
    elif args.mode == "stats":
        show_stats()
    elif args.mode == "crawl":
        run_crawl(args.menu)
    elif args.mode == "incremental":
        run_incremental(args.menu)
    elif args.mode == "process":
        run_process()
    elif args.mode == "embed":
        run_embed()
    elif args.mode == "ingest-files":
        run_ingest_files(args.path)
    elif args.mode == "all":
        logger.info("=== 전체 파이프라인 실행 ===")
        run_crawl(args.menu)
        run_process()
        run_embed()
        show_stats()
