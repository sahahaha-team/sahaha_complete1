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
"""

import os
import argparse
import logging
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


def run_incremental(menu_filter: str = None):
    """증분 크롤링: 변경된 페이지만 감지하여 업데이트"""
    from crawler.saha_crawler import SahaCrawler
    from database_db.database import Database
    from processor.data_cleaner import DataCleaner
    from processor.metadata_tagger import MetadataTagger
    from database_db.vector_store import VectorStore

    crawler = SahaCrawler(use_selenium=False)
    db = Database()
    cleaner = DataCleaner()
    tagger = MetadataTagger()
    vs = VectorStore()

    menus = {k: v for k, v in TARGET_MENUS.items() if menu_filter is None or k == menu_filter}

    stats = {"new": 0, "updated": 0, "unchanged": 0, "deleted": 0}
    changed_urls = []

    try:
        # 1. 현재 사이트 전체 크롤링
        current_pages = {}
        for menu_name, menu_path in menus.items():
            start_url = BASE_URL + menu_path
            pages = crawler.crawl_menu(menu_name, start_url, max_pages=MAX_PAGES_PER_MENU)
            for page in pages:
                current_pages[page.url] = page

        logger.info(f"현재 사이트 페이지 수: {len(current_pages)}개")

        # 2. 신규/변경 페이지 처리
        for url, page in current_pages.items():
            result = db.upsert_raw_page(page)
            stats[result] += 1
            if result in ("new", "updated"):
                changed_urls.append(url)
                logger.info(f"  [{result.upper()}] {page.title[:40]} - {url}")

        # 3. 사라진 페이지 삭제
        db_urls = db.get_all_urls()
        deleted_urls = db_urls - set(current_pages.keys())
        for url in deleted_urls:
            db.delete_page(url)
            stats["deleted"] += 1
            logger.info(f"  [DELETED] {url}")

        logger.info(
            f"증분 크롤링 완료 - "
            f"신규: {stats['new']}개 / 변경: {stats['updated']}개 / "
            f"삭제: {stats['deleted']}개 / 변경없음: {stats['unchanged']}개"
        )

        # 4. 변경된 페이지만 재처리
        if not changed_urls:
            logger.info("변경된 페이지 없음. 업데이트 불필요.")
            return stats

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

            chunks = cleaner.process(_P())
            if not chunks:
                continue
            tagged = tagger.tag_batch(chunks)
            all_tagged.extend(tagged)

        if all_tagged:
            db.save_chunks_bulk(all_tagged)

            import json
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
                    "keywords": json.dumps(metadata.get("keywords", []), ensure_ascii=False),
                    "summary": metadata.get("summary", ""),
                }
                new_chunk_pairs.append((_C(), meta))

            vs.add_chunks_batch(new_chunk_pairs, batch_size=50, db=db)
            logger.info(f"재처리 완료: {len(all_tagged)}개 청크 업데이트")

    finally:
        crawler.close()

    return stats


def run_process():
    """2단계: 정제 + LLM 태깅 → MySQL chunks 저장"""
    from database_db.database import Database, RawPage
    from processor.data_cleaner import DataCleaner
    from processor.metadata_tagger import MetadataTagger

    db = Database()
    cleaner = DataCleaner()
    tagger = MetadataTagger()

    with db.Session() as session:
        raw_pages = session.query(RawPage).all()

    logger.info(f"처리 대상: {len(raw_pages)}개 페이지")

    all_tagged = []
    for raw in tqdm(raw_pages, desc="정제 중"):
        class _P:
            url = raw.url
            title = raw.title
            content = raw.content
            category = raw.category
            sub_category = raw.sub_category

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
            "keywords": row.keywords or "[]",
            "summary": row.summary or "",
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


def run_web():
    """웹 서버 실행"""
    from app import run_server
    logger.info("=== 사하구청 AI 상담사 웹 서버 시작 ===")
    run_server()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="사하구청 AI 상담사")
    parser.add_argument(
        "--mode",
        choices=["crawl", "incremental", "process", "embed", "all", "stats", "web"],
        default="web",
        help="실행 모드 (기본: web)",
    )
    parser.add_argument("--menu", type=str, default=None,
                        help=f"특정 메뉴만 크롤링: {list(TARGET_MENUS.keys())}")
    args = parser.parse_args()

    if args.mode == "web":
        run_web()
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
    elif args.mode == "all":
        logger.info("=== 전체 파이프라인 실행 ===")
        run_crawl(args.menu)
        run_process()
        run_embed()
        show_stats()
