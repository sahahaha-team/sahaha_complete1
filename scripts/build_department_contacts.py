"""staff_directory.json에서 경량 부서·전화번호 전용 파일을 생성한다."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chatbot.contact_directory import DEFAULT_CONTACT_PATH, save_contact_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "staff_directory.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_CONTACT_PATH)
    args = parser.parse_args()

    staff_data = json.loads(args.source.read_text(encoding="utf-8"))
    output = save_contact_payload(staff_data, args.output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    print(json.dumps({
        "output": str(output),
        "departments": len(payload.get("departments") or []),
        "contacts": len(payload.get("contacts") or []),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
