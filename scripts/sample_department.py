"""부서 추출 결과의 분포와 NULL 청크의 본문 샘플 확인."""

import sys
import os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_db import get_supabase
from config import SUPABASE_SERVICE_KEY


def main():
    client = get_supabase(admin=bool(SUPABASE_SERVICE_KEY))

    # 추출된 부서명 분포
    rows = (
        client.table("processed_chunks")
        .select("department")
        .not_.is_("department", "null")
        .execute()
        .data
        or []
    )
    counter = Counter(r["department"] for r in rows)
    print(f"=== 추출된 부서 분포 (총 {len(rows)}건) ===")
    for dept, n in counter.most_common(15):
        print(f"  {dept}: {n}")

    # NULL 청크의 본문 끝부분 일부 샘플 (담당부서 표기가 본문에 있는지 사람이 확인)
    nulls = (
        client.table("processed_chunks")
        .select("url, content")
        .is_("department", "null")
        .limit(5)
        .execute()
        .data
        or []
    )
    print(f"\n=== NULL 청크 본문 끝 200자 샘플 5건 ===")
    for r in nulls:
        tail = (r.get("content") or "")[-300:]
        print(f"  URL: {r['url']}")
        print(f"  ...{tail}")
        print("  ---")


if __name__ == "__main__":
    main()
