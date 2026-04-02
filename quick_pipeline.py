"""태깅 건너뛰고 청크 정제 + 벡터 임베딩만 수행 (Gemini API 할당량 문제 우회)"""
import json
import logging
from tqdm import tqdm
from database_db.database import Database
from processor.data_cleaner import DataCleaner
from database_db.vector_store import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

db = Database()
cleaner = DataCleaner()

# 1단계: 정제 (태깅 없이 기본 메타데이터로 저장)
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

    chunks = cleaner.process(_P())
    if not chunks:
        continue

    for chunk in chunks:
        base_meta = {
            "url": chunk.url,
            "title": chunk.title,
            "category": chunk.category,
            "sub_category": chunk.sub_category,
            "service_type": "기타",
            "keywords": "[]",
            "summary": chunk.content[:50],
        }
        all_tagged.append((chunk, base_meta))

db.save_chunks_bulk(all_tagged)
logger.info(f"정제 완료: {len(all_tagged)}개 청크")

# 2단계: 벡터 임베딩
vs = VectorStore()
chunks = db.get_unembedded_chunks()
logger.info(f"임베딩 대상: {len(chunks)}개")

if chunks:
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
    logger.info(f"임베딩 완료: {len(chunk_meta_pairs)}개 벡터 저장")
else:
    logger.info("임베딩할 청크 없음")

logger.info("=== 파이프라인 완료 ===")
