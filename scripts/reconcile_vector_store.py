"""processed_chunks와 documents를 안전하게 동기화한다.

기본은 점검만 수행하며 --apply를 전달해야 변경한다. 삭제할 파생 벡터의
본문/메타데이터는 data/ 아래 JSON 백업으로 먼저 저장한다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from database_db import get_supabase
from database_db.vector_store import VectorStore
from processor.metadata_defaults import fallback_keywords


def _all_rows(client, table: str, columns: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        batch = client.table(table).select(columns).range(offset, offset + 999).execute().data or []
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        offset += 1000


def _keywords(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            return [value.strip()]
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="백업 후 실제 동기화")
    args = parser.parse_args()

    client = get_supabase(admin=True)
    chunks = _all_rows(
        client,
        "processed_chunks",
        "chunk_id,url,title,content,category,sub_category,service_type,department,keywords,summary,attachments,embedded",
    )
    documents = _all_rows(client, "documents", "id,content,metadata")
    chunk_by_id = {row["chunk_id"]: row for row in chunks}
    doc_by_id = {row["id"]: row for row in documents}

    missing_doc_ids = sorted(set(chunk_by_id) - set(doc_by_id))
    stale_doc_ids = sorted(set(doc_by_id) - set(chunk_by_id))
    common_ids = sorted(set(chunk_by_id) & set(doc_by_id))
    missing_keyword_ids = [
        chunk_id for chunk_id, row in chunk_by_id.items() if not _keywords(row.get("keywords"))
    ]

    print(f"processed_chunks={len(chunks)} documents={len(documents)}")
    print(f"missing_documents={len(missing_doc_ids)} stale_documents={len(stale_doc_ids)}")
    print(f"missing_keywords={len(missing_keyword_ids)}")
    if not args.apply:
        print("점검만 완료했습니다. 변경하려면 --apply를 사용하세요.")
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = ROOT / "data" / f"vector_reconcile_backup_{timestamp}.json"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(
        json.dumps([doc_by_id[doc_id] for doc_id in stale_doc_ids], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"backup={backup_path}")

    # 키워드가 비어 있는 처리 청크를 결정적 폴백으로 채운다.
    for chunk_id in missing_keyword_ids:
        row = chunk_by_id[chunk_id]
        keywords = fallback_keywords(row.get("content", ""), row.get("title", ""))
        row["keywords"] = json.dumps(keywords, ensure_ascii=False)
        client.table("processed_chunks").update({"keywords": row["keywords"]}).eq("chunk_id", chunk_id).execute()

    # 원본 처리 청크가 사라진 파생 벡터는 백업 후 제거한다.
    for offset in range(0, len(stale_doc_ids), 100):
        ids = stale_doc_ids[offset:offset + 100]
        if ids:
            client.table("documents").delete().in_("id", ids).execute()

    # 공통 문서의 메타데이터를 처리 청크 기준으로 동기화한다.
    for chunk_id in common_ids:
        row = chunk_by_id[chunk_id]
        meta = dict(doc_by_id[chunk_id].get("metadata") or {})
        meta.update({
            "url": row.get("url") or "",
            "title": row.get("title") or "",
            "category": row.get("category") or "",
            "sub_category": row.get("sub_category") or "",
            "service_type": row.get("service_type") or "기타",
            "department": row.get("department") or "",
            "keywords": row.get("keywords") or "[]",
            "summary": row.get("summary") or "",
            "attachments": row.get("attachments") or [],
        })
        client.table("documents").update({"metadata": meta}).eq("id", chunk_id).execute()

    # 처리됐지만 벡터가 없는 청크를 새로 임베딩한다.
    if missing_doc_ids:
        vector_store = VectorStore(admin=True)
        pairs = []
        for chunk_id in missing_doc_ids:
            row = chunk_by_id[chunk_id]

            class Chunk:
                pass

            chunk = Chunk()
            chunk.chunk_id = chunk_id
            chunk.content = row.get("content") or ""
            metadata = {
                "url": row.get("url") or "",
                "title": row.get("title") or "",
                "category": row.get("category") or "",
                "sub_category": row.get("sub_category") or "",
                "service_type": row.get("service_type") or "기타",
                "department": row.get("department") or "",
                "keywords": row.get("keywords") or "[]",
                "summary": row.get("summary") or "",
                "attachments": row.get("attachments") or [],
            }
            pairs.append((chunk, metadata))
        vector_store.add_chunks_batch(pairs, batch_size=50)

    # documents에 존재하는 모든 처리 청크는 embedded=true로 정정한다.
    synced_ids = common_ids + missing_doc_ids
    for offset in range(0, len(synced_ids), 100):
        ids = synced_ids[offset:offset + 100]
        if ids:
            client.table("processed_chunks").update({"embedded": True}).in_("chunk_id", ids).execute()

    print(
        f"완료: keywords={len(missing_keyword_ids)} backfill, "
        f"vectors={len(missing_doc_ids)} added, stale={len(stale_doc_ids)} removed"
    )


if __name__ == "__main__":
    main()
