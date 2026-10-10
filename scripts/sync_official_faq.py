"""resources/official_faq.json을 Supabase official_faq 테이블과 동기화한다."""

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

from database_db import get_supabase


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--faq", type=Path, default=ROOT / "resources" / "official_faq.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    items = json.loads(args.faq.read_text(encoding="utf-8"))
    rows = [{
        "id": item["id"],
        "question": item["question"],
        "approved_answer": item["answer"],
        "source_url": item["url"],
        "category": item.get("category", "기타"),
        "keywords": item.get("keywords", []),
        "is_time_sensitive": bool(item.get("is_time_sensitive", False)),
        "verified_at": item.get("verified_at") or None,
    } for item in items]

    print(f"official_faq={len(rows)} apply={args.apply}")
    if not args.apply:
        return 0

    client = get_supabase(admin=True)
    for offset in range(0, len(rows), 50):
        client.table("official_faq").upsert(
            rows[offset:offset + 50], on_conflict="id"
        ).execute()
    print("sync_complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
