"""
Supabase 마이그레이션 적용 점검.

확인 항목:
  - raw_pages.etag
  - raw_pages.last_modified
  - processed_chunks.department

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


def main():
    client = get_supabase(admin=bool(SUPABASE_SERVICE_KEY))
    print("=" * 60)
    print("Supabase Migration Check")
    print("=" * 60)

    checks = [
        ("raw_pages", "etag"),
        ("raw_pages", "last_modified"),
        ("processed_chunks", "department"),
    ]

    all_ok = True
    for table, col in checks:
        ok, msg = _select_one(client, table, col)
        mark = "OK " if ok else "FAIL"
        print(f"[{mark}] {table}.{col}: {msg}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\n누락된 컬럼이 있습니다. setup_supabase.sql의 ALTER TABLE 문을")
        print("Supabase Dashboard > SQL Editor에서 실행해주세요.")
        sys.exit(1)

    print("\n--- 백필 진척도 ---")
    for table, col in checks:
        filled, total = _count_filled(client, table, col)
        if total < 0:
            print(f"  {table}.{col}: 집계 실패")
            continue
        pct = (filled / total * 100) if total else 0
        print(f"  {table}.{col}: {filled}/{total} ({pct:.1f}%)")

    print("\n결과: 모든 컬럼 존재함. 다음 단계 진행 가능.")


if __name__ == "__main__":
    main()
