"""Immediate fire reporting guidance verified against Saha-gu's official page.

Emergency responses never invoke models or DB, and never store the input.
Source checked: 2026-10-07. Page last updated: 2026-06-10.
"""
import re

from chatbot.query_subject import normalize_query

FIRE_SOURCE_URL = "https://www.saha.go.kr/portal/contents.do?mId=0410020200"
ADMINISTRATIVE = re.compile(r"예방|교육|훈련|점검|검사|허가|허위|과태료|처벌|벌금|보상|지원금|증명|보험|통계|건수|보고서")
ONGOING_FIRE = re.compile(r"불(?:이)?(?:났|난|나고|나서|붙|남)|화재(?:가)?(?:났|발생|나고)")


def answer_emergency_question(query: str) -> dict | None:
    normalized = normalize_query(query)
    text = re.sub(r"\s+", "", normalized)
    ongoing = bool(ONGOING_FIRE.search(text))
    # Incident wording also appears in claims/statistics about past fires.
    # Those questions need administrative evidence rather than report routing.
    if ADMINISTRATIVE.search(text):
        return None
    if not ongoing and "화재" not in text:
        return None
    if not ongoing and not re.search(r"신고|119|긴급|대피|대처|어떻게|어디|연락|전화", text):
        return None
    answer = (
        "**안전한 곳으로 대피한 뒤 119에 신고하세요.**\n"
        "불이 난 위치(주소·주변 건물)와 상황을 알리고, 소방서에서 알았다고 할 때까지 전화를 끊지 마세요."
    )
    if normalized != query:
        answer += "\n\n‘화제’는 신고 문맥상 ‘화재’로 이해했습니다."
    return {
        "answer": answer,
        "sources": [{"title": "사하구청 화재 행동요령·119 신고 방법", "url": FIRE_SOURCE_URL,
                     "category": "재난안전", "service_type": "긴급신고", "department": "",
                     "contact": "119", "source_type": "official_page", "checked_at": "2026-10-07"}],
        "is_clarification": False, "degraded": False, "degraded_reason": None,
        "evidence": {"status": "official", "label": "공식 화재 신고 안내", "official_source_count": 1},
        "suggested_questions": [],
    }
