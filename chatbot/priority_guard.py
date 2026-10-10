"""Guardrails for high-priority resident service answers.

The LLM remains responsible for wording the response.  For the small set of
services whose facts must be exact, this module verifies that every required
fact from the curated official answer is present and falls back to that answer
when the generated text is incomplete.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


_REQUIRED_FACTS_BY_MENU = {
    "0405050000": [
        "월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일",
        "음식물쓰레기", "재활용품", "19:00", "22:00",
    ],
    "1207000000": [
        "3개월", "매월 1일", "09:00", "4세", "13세", "무료", "10명", "12명",
        "051-271-6835",
    ],
    "0408030000": ["통합예약", "온라인", "사하구민", "무료", "051-220-4834"],
    "0103000000": ["09:00", "18:00", "12:00", "13:00"],
    "0203020000": ["09:00", "11:30", "13:00", "17:30"],
}


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def enforce_priority_facts(answer: str, results: Iterable[Any]) -> str:
    """Return *answer* when complete, otherwise the verified approved answer."""
    normalized_answer = _normalized(answer)

    for result in results or []:
        metadata = getattr(result, "metadata", None)
        if metadata is None and isinstance(result, dict):
            metadata = result.get("metadata", {})
        metadata = metadata or {}

        if metadata.get("source_priority") != "priority_service":
            continue

        approved_answer = str(metadata.get("approved_answer") or "").strip()
        required_facts = metadata.get("required_facts") or []
        if not required_facts:
            source_url = str(metadata.get("url") or metadata.get("source_url") or "")
            for menu_id, facts in _REQUIRED_FACTS_BY_MENU.items():
                if menu_id in source_url:
                    required_facts = facts
                    break
        if not approved_answer:
            return answer

        if not answer.strip() or any(
            _normalized(fact) not in normalized_answer for fact in required_facts
        ):
            return approved_answer
        return answer

    return answer
