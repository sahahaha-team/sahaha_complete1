"""부서 메타데이터를 원문 근거로 검증하고 잘못된 추정을 제거한다.

기본은 점검만 수행한다. --apply를 지정하면 processed_chunks와 documents의
department를 같은 값으로 동기화한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chatbot.dept_directory import (
    correct_dept,
    department_is_supported,
    extract_explicit_department,
)
from database_db import get_supabase


def _all_rows(client, table: str, columns: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        batch = client.table(table).select(columns).range(offset, offset + 999).execute().data or []
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        offset += 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    client = get_supabase(admin=True)
    pages = _all_rows(client, "raw_pages", "url,content")
    chunks = _all_rows(client, "processed_chunks", "chunk_id,url,title,content,department")
    documents = _all_rows(client, "documents", "id,metadata")
    page_hints = {
        row["url"]: extract_explicit_department(row.get("content") or "")
        for row in pages
    }
    document_meta = {row["id"]: dict(row.get("metadata") or {}) for row in documents}

    changes: list[tuple[str, str | None, str | None]] = []
    for row in chunks:
        old = correct_dept(row.get("department") or "") or None
        hint = page_hints.get(row.get("url") or "") or ""
        evidence_text = f"{row.get('title') or ''} {row.get('content') or ''}"
        new = hint or (old if old and department_is_supported(old, evidence_text) else None)
        if new != old:
            changes.append((row["chunk_id"], old, new))

    print(f"chunks={len(chunks)} department_changes={len(changes)}")
    if not args.apply:
        print("점검만 완료했습니다. 변경하려면 --apply를 사용하세요.")
        return

    for chunk_id, _old, new in changes:
        client.table("processed_chunks").update({"department": new}).eq("chunk_id", chunk_id).execute()
        if chunk_id in document_meta:
            metadata = document_meta[chunk_id]
            metadata["department"] = new or ""
            client.table("documents").update({"metadata": metadata}).eq("id", chunk_id).execute()

    print(f"완료: {len(changes)}개 부서 메타데이터 검증·동기화")


if __name__ == "__main__":
    main()
