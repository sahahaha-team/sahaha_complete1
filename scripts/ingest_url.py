"""공식 사하구청 URL 한 건을 수집·정제·태깅·임베딩한다.

깊은 메뉴나 평가용 핵심 페이지를 증분 BFS에 즉시 시드할 때 사용한다.
기본은 LLM 자동 태깅이며, 외부 API 한도가 부족한 운영 복구 상황에서는
``--fallback-only``로 결정적 메타데이터 보완을 사용할 수 있다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from crawler.saha_crawler import SahaCrawler
from database_db.database import Database
from database_db.vector_store import VectorStore
from processor.data_cleaner import DataCleaner
from processor.metadata_tagger import MetadataTagger, ensure_metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--category", default="분야별정보")
    parser.add_argument("--fallback-only", action="store_true")
    args = parser.parse_args()

    hostname = (urlparse(args.url).hostname or "").lower()
    if not (hostname == "saha.go.kr" or hostname.endswith(".saha.go.kr")):
        raise SystemExit("공식 saha.go.kr URL만 적재할 수 있습니다.")

    crawler = SahaCrawler(use_selenium=False)
    try:
        fetched = crawler.fetch_page(args.url)
        if not fetched or fetched.get("status") != "ok" or not fetched.get("html"):
            raise SystemExit(f"페이지 수집 실패: {fetched}")
        page = crawler.parse_page(fetched["html"], args.url, args.category)
        page.etag = fetched.get("etag")
        page.last_modified = fetched.get("last_modified")
        if not page.content:
            raise SystemExit("유효한 본문을 찾지 못했습니다.")

        db = Database(admin=True)
        state = db.upsert_raw_page(page)
        cleaner = DataCleaner(db=db)
        chunks = cleaner.process(page)
        if not chunks and state == "unchanged":
            print("변경 없음: 기존 청크를 유지합니다.")
            return
        if not chunks:
            raise SystemExit("정제 후 유효한 청크가 없습니다.")

        if args.fallback_only:
            tagged = [(chunk, ensure_metadata({}, chunk)) for chunk in chunks]
        else:
            tagged = MetadataTagger().tag_batch(chunks)

        db.save_chunks_bulk(tagged)
        pairs = []
        for chunk, metadata in tagged:
            pairs.append((chunk, {
                "url": chunk.url,
                "title": chunk.title,
                "category": chunk.category,
                "sub_category": chunk.sub_category,
                "service_type": metadata.get("service_type") or "기타",
                "department": metadata.get("department") or "",
                "keywords": metadata.get("keywords") or [],
                "summary": metadata.get("summary") or "",
                "attachments": chunk.attachments,
            }))
        VectorStore(admin=True).add_chunks_batch(pairs, batch_size=50, db=db)
        print(f"state={state} chunks={len(chunks)} url={args.url}")
    finally:
        crawler.close()


if __name__ == "__main__":
    main()
