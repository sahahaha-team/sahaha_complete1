"""
Supabase 마이그레이션 적용 점검.

확인 항목:
  - raw_pages.etag
  - raw_pages.last_modified
  - raw_pages.last_checked_at
  - raw_pages.raw_html
  - processed_chunks.department
  - crawl_runs / ingestion_jobs / official_faq 테이블
  - conversation_logs / crawl_runs / ingestion_jobs 익명 SELECT 차단

각 컬럼이 실제로 존재하는지 SELECT 한 줄로 검증하고,
백필 진척도(채워진 행 수 / 전체 행 수)도 함께 출력한다.

사용: python scripts/check_migration.py
"""

import sys
import os

# 프로젝트 루트를 import path에 추가 (scripts/ 하위에서 실행 시)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_db import get_supabase
from config import SUPABASE_SERVICE_KEY


def _select_one(client, table: str, col: str) -> tuple[bool, str]:
    """해당 컬럼이 select 가능한지 검사."""
    try:
        client.table(table).select(col).limit(1).execute()
        return True, "OK"
    except Exception as e:
        return False, str(e).splitlines()[0][:200]


def _count_filled(client, table: str, col: str) -> tuple[int, int]:
    """컬럼이 NULL/빈문자열이 아닌 행 수와 전체 행 수."""
    try:
        total = client.table(table).select("*", count="exact", head=True).execute().count or 0
        filled = (
            client.table(table)
            .select("*", count="exact", head=True)
            .not_.is_(col, "null")
            .execute()
            .count
            or 0
        )
        return filled, total
    except Exception:
        return -1, -1


def _anon_select_is_blocked(client, table: str) -> tuple[bool, str]:
    """anon 역할이 민감한 운영 테이블을 SELECT하지 못하는지 검사."""
    try:
        client.table(table).select("*").limit(1).execute()
        return False, "anon SELECT가 허용되어 있음"
    except Exception as e:
        return True, str(e).splitlines()[0][:200]


def main():
    if not SUPABASE_SERVICE_KEY:
        print("[FAIL] SUPABASE_SERVICE_KEY가 없어 관리자 스키마 점검을 수행할 수 없습니다.")
        sys.exit(1)

    admin_client = get_supabase(admin=True)
    anon_client = get_supabase(admin=False)
    print("=" * 60)
    print("Supabase Migration Check")
    print("=" * 60)

    checks = [
        ("raw_pages", "etag"),
        ("raw_pages", "last_modified"),
        ("raw_pages", "last_checked_at"),
        ("raw_pages", "raw_html"),
        ("processed_chunks", "department"),
        ("crawl_runs", "id"),
        ("ingestion_jobs", "id"),
        ("official_faq", "id"),
    ]

    all_ok = True
    for table, col in checks:
        ok, msg = _select_one(admin_client, table, col)
        mark = "OK " if ok else "FAIL"
        print(f"[{mark}] {table}.{col}: {msg}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\n누락된 테이블 또는 컬럼이 있습니다.")
        print("누락 항목에 따라 아래 마이그레이션을 SQL Editor에서 실행해주세요.")
        print("- scripts/migration_crawl_audit_and_security.sql")
        print("- scripts/migration_official_faq_and_html.sql")
        sys.exit(1)

    faq_count = (
        admin_client.table("official_faq")
        .select("id", count="exact", head=True)
        .execute()
        .count
        or 0
    )
    print(f"[{'OK ' if faq_count == 100 else 'FAIL'}] official_faq rows: {faq_count}/100")
    if faq_count != 100:
        all_ok = False

    print("\n--- RLS / anon 접근 차단 ---")
    protected_tables = ["conversation_logs", "crawl_runs", "ingestion_jobs"]
    for table in protected_tables:
        blocked, msg = _anon_select_is_blocked(anon_client, table)
        mark = "OK " if blocked else "FAIL"
        print(f"[{mark}] anon SELECT {table}: {'차단됨' if blocked else msg}")
        if not blocked:
            all_ok = False

    print("\n--- 백필 진척도 ---")
    for table, col in checks:
        filled, total = _count_filled(admin_client, table, col)
        if total < 0:
            print(f"  {table}.{col}: 집계 실패")
            continue
        pct = (filled / total * 100) if total else 0
        print(f"  {table}.{col}: {filled}/{total} ({pct:.1f}%)")

    if not all_ok:
        print("\n결과: RLS 정책이 요구사항을 충족하지 않습니다.")
        sys.exit(1)

    print("\n결과: 스키마와 익명 접근 차단이 요구사항을 충족합니다.")


if __name__ == "__main__":
    main()
