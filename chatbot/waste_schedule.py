"""Verified answers for Saha-gu household-waste disposal schedules."""

from __future__ import annotations

import re
from typing import Any


WASTE_GUIDE_URL = "https://www.saha.go.kr/portal/contents.do?mId=0405050101"
WASTE_GUIDE_TITLE = "생활쓰레기 배출요령"


def _source() -> dict[str, str]:
    return {
        "title": WASTE_GUIDE_TITLE,
        "url": WASTE_GUIDE_URL,
        "category": "환경·청소",
        "department": "자원순환과",
    }


def _result(answer: str) -> dict[str, Any]:
    source = _source()
    return {
        "answer": answer,
        "sources": [source],
        "evidence": [
            {
                "title": source["title"],
                "url": source["url"],
                "snippet": answer,
                "method": "verified_waste_schedule",
            }
        ],
        "answer_method": "verified_waste_schedule",
        "verified": True,
        "degraded": False,
        "answer_details": "",
    }


def answer_waste_schedule(query: str) -> dict[str, Any] | None:
    """Return a direct answer for common schedule questions using the official table.

    This intentionally does not handle bulky waste, construction waste, appliances,
    fees, or collection applications; those require their own official guidance.
    """

    normalized = re.sub(r"\s+", "", (query or "").lower())
    if not normalized:
        return None

    excluded = (
        "대형폐기물",
        "폐가전",
        "가전제품",
        "건설폐기물",
        "사업장폐기물",
        "수수료",
        "신청",
        "스티커",
    )
    if any(word in normalized for word in excluded):
        return None

    waste_words = ("쓰레기", "폐기물", "종량제", "재활용", "분리수거", "음식물")
    schedule_words = ("언제", "요일", "몇시", "시간", "무슨날", "배출", "버려", "버리")
    if not any(word in normalized for word in waste_words):
        return None
    if not any(word in normalized for word in schedule_words):
        return None

    if "음식물" in normalized:
        return _result(
            "음식물쓰레기는 **화·목·일요일 19:00~22:00**에 물기를 제거한 뒤 "
            "전용 용기에 담아 배출하세요. **금·토요일은 배출하지 않습니다.**"
        )

    if "재활용" in normalized or "분리수거" in normalized:
        return _result(
            "재활용품은 **월·수요일 19:00~22:00**에 품목별로 분리해 배출하세요. "
            "월요일과 수요일의 세부 품목이 다르며, **금·토요일은 배출하지 않습니다.** "
            "품목을 말씀해 주시면 해당 배출 요일을 바로 안내해 드릴게요."
        )

    if "불연" in normalized:
        return _result(
            "불연성 일반쓰레기는 **수요일 19:00~22:00**에 전용 마대에 담아 "
            "대문 앞(연립주택은 1층 출입구 밖)에 배출하세요."
        )

    if any(word in normalized for word in ("일반쓰레기", "생활쓰레기", "종량제", "쓰레기")):
        return _result(
            "가연성 일반쓰레기는 **화·목·일요일 19:00~22:00**에 종량제봉투에 담아 "
            "대문 앞(연립주택은 1층 출입구 밖)에 배출하세요. "
            "불연성 일반쓰레기는 **수요일 같은 시간**에 배출하며, "
            "**금·토요일은 배출하지 않습니다.**"
        )

    return None
