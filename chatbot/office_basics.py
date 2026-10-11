"""Verified, stable Saha-gu office location guidance."""

from __future__ import annotations

import re


OFFICE_ADDRESS = "부산광역시 사하구 낙동대로398번길 12(당리동)"
OFFICE_PHONE = "051-220-4000"
LOCATION_URL = "https://www.saha.go.kr/portal/contents.do?mId=0604050000"
PHONE_URL = "https://www.saha.go.kr/portal/contents.do?mId=0604060000"


def answer_office_basics(query: str) -> dict | None:
    """Answer the head-office location directly from verified official facts."""
    compact = re.sub(r"[^0-9a-z가-힣]", "", (query or "").lower())
    mentions_office = any(term in compact for term in ("사하구청", "구청"))
    asks_location = any(term in compact for term in ("위치", "주소", "어디", "찾아가", "오시는길"))
    if not (mentions_office and asks_location):
        return None

    asks_contact = any(term in compact for term in ("연락처", "전화", "대표번호", "문의번호"))
    answer = (
        f"사하구청은 **{OFFICE_ADDRESS}**에 있습니다. "
        "도시철도를 이용하면 **당리역 5번 출구**에서 찾아갈 수 있습니다."
    )
    sources = [{
        "title": "사하구청 찾아오시는 길",
        "url": LOCATION_URL,
        "category": "official_page",
        "service_type": "구청 안내",
        "department": "",
        "contact": "",
        "attachments": [],
    }]
    if asks_contact:
        answer += f"\n\n사하구청 대표전화는 **{OFFICE_PHONE}**입니다."
        sources.append({
            "title": "사하구청 대표전화",
            "url": PHONE_URL,
            "category": "official_page",
            "service_type": "구청 안내",
            "department": "",
            "contact": OFFICE_PHONE,
            "attachments": [],
        })

    return {
        "answer": answer,
        "answer_details": "",
        "sources": sources,
        "is_clarification": False,
        "degraded": False,
        "degraded_reason": None,
        "evidence": {
            "status": "official",
            "label": "공식 구청 기본정보 확인됨",
            "official_source_count": len(sources),
            "answer_method": "verified_office_basics",
        },
        "suggested_questions": ["사하구청 민원실 운영시간 알려줘"],
    }
