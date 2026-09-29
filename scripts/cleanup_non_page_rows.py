"""크롤링 DB에 일반 페이지로 잘못 들어온 파일/이미지 행을 안전하게 정리한다.

기본은 진단만 수행한다. ``--apply`` 시 삭제 전 전체 행을 data/ 아래 JSON으로
백업하고 raw_pages, processed_chunks, documents를 URL 기준으로 함께 정리한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from database_db.database import Database
from processor.data_cleaner import is_non_page_url


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = Database(admin=True)
    rows = db.client.table("raw_pages").select("*").range(0, 9999).execute().data or []
    targets = [row for row in rows if is_non_page_url(row.get("url") or "")]
    total_chars = sum(len(row.get("content") or "") for row in targets)
    print(f"non_page_rows={len(targets)} content_chars={total_chars}")
    for row in sorted(targets, key=lambda value: len(value.get("content") or ""), reverse=True):
        print(f"{len(row.get('content') or ''):>9}  {row.get('url')}")

    if not args.apply or not targets:
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = ROOT / "data" / f"non_page_backup_{timestamp}.json"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")

    for row in targets:
        db.delete_page(row["url"])

    print(f"deleted={len(targets)} backup={backup_path}")


if __name__ == "__main__":
    main()
