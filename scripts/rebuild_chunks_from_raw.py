"""raw_pages에서 누락된 처리 청크를 복구하고 최신 본문으로 재임베딩한다.

동일 chunk_id의 기존 벡터 메타데이터가 있으면 LLM 태그를 보존하고, 새 청크나
누락 필드는 결정적 폴백으로 채운다. --apply 없이는 건수만 계산한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from database_db.database import Database
from database_db.vector_store import VectorStore
from processor.data_cleaner import DataCleaner
from processor.metadata_tagger import ensure_metadata


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return [value]
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = Database(admin=True)
    cleaner = DataCleaner(db=db)
    pages = db.get_all_raw_pages()
    docs = db.client.table("documents").select("id,metadata").range(0, 9999).execute().data or []
    doc_meta = {row["id"]: dict(row.get("metadata") or {}) for row in docs}

    recovered = []
    for raw in pages:
        chunks = cleaner.process(raw)
        for chunk in chunks:
            previous = doc_meta.get(chunk.chunk_id, {})
            previous["keywords"] = _as_list(previous.get("keywords"))
            previous["target_audience"] = _as_list(previous.get("target_audience"))
            recovered.append((chunk, ensure_metadata(previous, chunk)))

    print(f"raw_pages={len(pages)} missing_chunks={len(recovered)}")
    if not args.apply:
        return
    if not recovered:
        print("복구할 청크가 없습니다.")
        return

    db.save_chunks_bulk(recovered)
    pairs = []
    for chunk, metadata in recovered:
        pairs.append((chunk, {
            "url": chunk.url,
            "title": chunk.title,
            "category": chunk.category,
            "sub_category": chunk.sub_category,
            "service_type": metadata.get("service_type") or "기타",
            "department": metadata.get("department") or "",
            "keywords": json.dumps(metadata.get("keywords") or [], ensure_ascii=False),
            "summary": metadata.get("summary") or "",
            "attachments": chunk.attachments,
        }))
    VectorStore(admin=True).add_chunks_batch(pairs, batch_size=50, db=db)
    print(f"복구 완료: {len(recovered)}개 청크")


if __name__ == "__main__":
    main()
