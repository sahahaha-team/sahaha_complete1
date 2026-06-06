"""
부서(department) 컬럼이 NULL인 기존 청크만 골라 LLM으로 재태깅.

전체 run_process는 모든 청크를 재처리(삭제→재생성)하지만,
이 스크립트는 NULL 부서만 골라 department 컬럼만 부분 UPDATE한다.
- Groq 무료 티어(RPM 30) 부담 최소화
- 기존 태깅 결과(service_type, keywords 등)는 그대로 보존
- 본문에 부서가 명시되지 않은 청크는 NULL 유지(환각 방지)

사용:
  python scripts/retag_departments.py            # 전체 처리
  python scripts/retag_departments.py --limit 20 # 우선 20개만 테스트
  python scripts/retag_departments.py --dry-run  # LLM 호출/UPDATE 없이 후보만 출력
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_db import get_supabase
from config import SUPABASE_SERVICE_KEY
from processor.metadata_tagger import MetadataTagger, BATCH_SIZE, BATCH_DELAY_SEC


class _ChunkObj:
    """MetadataTagger.tag_batch가 기대하는 chunk 인터페이스(필요 속성만)."""
    def __init__(self, row: dict):
        self.chunk_id = row["chunk_id"]
        self.content = row.get("content") or ""
        self.title = row.get("title") or ""
        self.url = row.get("url") or ""
        self.category = row.get("category") or ""
        self.sub_category = row.get("sub_category") or ""
        self.chunk_index = row.get("chunk_index") or 0
        self.total_chunks = row.get("total_chunks") or 1


def fetch_null_department_chunks(client) -> list[dict]:
    rows = (
        client.table("processed_chunks")
        .select("chunk_id, content, title, url, category, sub_category, chunk_index, total_chunks")
        .is_("department", "null")
        .execute()
        .data
        or []
    )
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="처리할 최대 청크 수")
    ap.add_argument("--dry-run", action="store_true", help="LLM 호출/DB 업데이트 없이 후보만 출력")
    args = ap.parse_args()

    if not SUPABASE_SERVICE_KEY:
        print("SUPABASE_SERVICE_KEY 필요 (RLS 우회 UPDATE)")
        sys.exit(1)

    client = get_supabase(admin=True)
    rows = fetch_null_department_chunks(client)
    print(f"부서 NULL 청크: {len(rows)}개")

    if args.limit:
        rows = rows[: args.limit]
        print(f"--limit {args.limit} 적용 → {len(rows)}개만 처리")

    if not rows:
        print("처리할 청크 없음. 종료.")
        return

    if args.dry_run:
        print("--- dry-run: 후보 청크 (앞 10개) ---")
        for r in rows[:10]:
            print(f"  [{r['chunk_id']}] {r.get('title','')[:40]}")
        return

    tagger = MetadataTagger()
    if not tagger.llm:
        print("LLM 미초기화 — GROQ_API_KEY 확인 필요")
        sys.exit(1)

    chunks = [_ChunkObj(r) for r in rows]
    print(f"LLM 재태깅 시작 (batch_size={BATCH_SIZE}, delay={BATCH_DELAY_SEC}s)...")

    tagged = tagger.tag_batch(chunks)

    updated, kept_null, failed = 0, 0, 0
    for chunk, meta in tagged:
        dept = meta.get("department")
        # 빈 문자열, 공백, "null" 문자열 등 정규화
        if isinstance(dept, str):
            dept_norm = dept.strip()
            if dept_norm.lower() in ("", "null", "none", "n/a"):
                dept_norm = None
        else:
            dept_norm = None

        if dept_norm is None:
            kept_null += 1
            continue

        try:
            client.table("processed_chunks").update(
                {"department": dept_norm}
            ).eq("chunk_id", chunk.chunk_id).execute()
            updated += 1
        except Exception as e:
            print(f"  UPDATE 실패 ({chunk.chunk_id}): {e}")
            failed += 1
        # Supabase API에 너무 빠른 연속 UPDATE 방지
        time.sleep(0.05)

    print("\n=== 재태깅 완료 ===")
    print(f"  업데이트:  {updated}")
    print(f"  NULL 유지: {kept_null} (본문에 부서 미명시 — 환각 방지)")
    print(f"  실패:      {failed}")
    print(f"  합계:      {len(tagged)}")


if __name__ == "__main__":
    main()
