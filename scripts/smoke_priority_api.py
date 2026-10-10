"""Smoke-test high-priority resident questions against a running local server."""

from __future__ import annotations

import json
import sys

import requests


BASE_URL = "http://127.0.0.1:5000"

CASES = [
    (
        "요일별 쓰레기 배출 방법 알려줘",
        "0405050000",
        ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일", "음식물쓰레기", "19:00", "22:00"],
    ),
    (
        "소방 체험 예약 방법 알려줘",
        "1207000000",
        ["3개월", "매월 1일", "09:00", "4세", "13세", "무료", "051-271-6835"],
    ),
    (
        "작은도서관 교육 프로그램 예약 방법 알려줘",
        "0408030000",
        ["통합예약", "온라인", "사하구민", "무료", "051-220-4834"],
    ),
    (
        "보건소 운영시간과 점심시간 알려줘",
        "0103000000",
        ["09:00", "18:00", "12:00", "13:00"],
    ),
    (
        "보건소 성인 백신 접종 시간 알려줘",
        "0203020000",
        ["09:00", "11:30", "13:00", "17:30"],
    ),
]


def chat(session: requests.Session, message: str) -> dict:
    response = session.post(f"{BASE_URL}/api/chat", json={"message": message}, timeout=120)
    response.raise_for_status()
    return response.json()


def main() -> int:
    failures = []
    results = []
    for question, menu_id, facts in CASES:
        session = requests.Session()
        data = chat(session, question)
        answer = data.get("answer", "")
        urls = [source.get("url", "") for source in data.get("sources", [])]
        missing = [fact for fact in facts if fact not in answer]
        passed = not missing and any(menu_id in url for url in urls)
        results.append({"question": question, "passed": passed, "missing": missing, "urls": urls})
        if not passed:
            failures.append(question)

    # One-condition clarification must retain the same browser session.
    session = requests.Session()
    first = chat(session, "불법주정차 담당자 전화번호 알려줘")
    second = chat(session, "민원처리")
    multiturn_passed = (
        bool(first.get("is_clarification"))
        and "051-220-4562" in second.get("answer", "")
        and any("staff/list.do" in s.get("url", "") for s in second.get("sources", []))
    )
    results.append({"question": "불법주정차 → 민원처리", "passed": multiturn_passed})
    if not multiturn_passed:
        failures.append("불법주정차 → 민원처리")

    print(json.dumps({"passed": len(results) - len(failures), "total": len(results), "results": results}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
