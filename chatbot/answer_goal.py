"""Requested answer fields, kept separate from service-topic evidence."""
from __future__ import annotations

import re

from chatbot.question_intent import asks_location, asks_opening_hours

GOAL_WORDS = {
    "reference": ("홈페이지", "페이지", "링크", "현황도", "지도", "조회", "확인", "자세히보기", "다운로드"),
    "method": ("방법", "접수", "예약", "신고", "신청", "이용", "발급", "절차", "제출", "등록", "로그인", "회원가입", "전화", "콜센터", "인터넷", "인증", "표기", "작성", "선택", "입력", "조회"),
    "eligibility": ("대상", "조건", "자격", "해당", "소유", "보유", "이상", "이하"),
    "cost": ("수수료", "요금", "비용", "금액", "원", "무료", "무상", "유료"),
    "documents": ("서류", "준비", "지참", "구비", "신분증", "신청서"),
    "schedule": ("시간", "기간", "일정", "주기", "매년", "매월", "연 ", "월 ", "일", "년"),
    "location": ("장소", "주소", "위치", "방문", "기관"),
    "hours": ("시간", "휴무", "평일", "주말"),
    "services": ("내용", "운영", "진료", "검사", "상담", "제공", "지원"),
}


def answer_goal(query: str) -> str | None:
    if any(word in query.replace(" ", "") for word in ("어떤서비스", "어떤진료", "무슨서비스", "어떤지원")):
        return "services"
    link_requested = "링크" in query and not re.search(r'링크\s*(?:는|가|도)?\s*(?:말고|필요\s*없|제외|빼고)', query)
    if (link_requested or ("어디" in query and any(word in query for word in (
            "확인", "찾아볼", "찾아보", "조회", "볼 수", "볼수", "보나요", "현황도", "지도", "사이트")))):
        return "reference"
    if asks_opening_hours(query):
        return "hours"
    if asks_location(query):
        return "location"
    if any(word in query for word in ("서류", "준비물", "구비", "준비해야")) and not any(word in query for word in ("발급", "신청", "어떻게")):
        return "documents"
    if any(word in query for word in ("준비물", "구비", "준비해야", "필요한 서류")):
        return "documents"
    if any(word in query for word in ("비용", "수수료", "요금", "얼마", "금액")) and not any(word in query for word in ("자주", "무료", "무상", "부담")):
        return "cost"
    if any(word in query for word in ("대상", "조건", "자격", "누가", "누구", "몇 살", "몇살")):
        return "eligibility"
    if any(word in query for word in ("언제", "기간", "며칠", "주기", "자주", "날짜", "몇 번")):
        return "schedule"
    if any(word in query for word in ("방법", "어떻게", "하는 법", "받는 법", "신청", "접수", "신고", "발급")):
        return "method"
    if "받을 수" in query:
        return "eligibility"
    return None
