"""Grounded summaries for named public programs and classes."""

from __future__ import annotations

import re

from chatbot.answer_goal import answer_goal, asks_for_detail
from chatbot.faq_targets import find_program_service
from chatbot.query_subject import compact


PROGRAM_CUES = ("프로그램", "강좌", "교실", "체험", "교육")
OVERVIEW_CUES = ("설명", "소개", "어떤", "무슨", "뭐", "있", "내용", "알려")
FIELD_PATTERN = re.compile(
    r"(?:이용|교육|신청)?대상|(?:이용|수강)?료|운영시간|이용시간|체험시간|"
    r"운영기간|운영내용|사업내용|프로그램내용|신청방법|예약|문의|전화번호|주소|장소"
)

PROGRAM_CATALOG = (
    ("fire", ("소방", "소방특화", "들락날락"), "소방특화 들락날락 체험",
     "어린이가 가상재난·심폐소생술·화재진압·비상대피 등을 체험하는 소방안전 프로그램입니다.",
     "https://www.saha.go.kr/reserve/contents.do?mId=1207000000"),
    ("library", ("작은도서관",), "작은도서관 교육 프로그램",
     "작은도서관의 독서·교육 프로그램으로, 모집 과정은 통합예약에서 확인할 수 있습니다.",
     "https://www.saha.go.kr/portal/contents.do?mId=0408030000"),
    ("lifelong", ("평생학습관", "평생학습"), "평생학습관 프로그램",
     "주민을 위한 평생교육 강좌와 학습 과정의 모집 정보를 안내하는 프로그램입니다.",
     "https://www.saha.go.kr/portal/contents.do?mId=0408000000"),
    ("digital", ("디지털", "컴퓨터"), "디지털·컴퓨터 교육",
     "주민이 이용할 수 있는 디지털·컴퓨터 교육 과정과 신청 정보를 안내합니다.",
     "https://www.saha.go.kr/portal/contents.do?mId=0408020000"),
    ("health", ("운동", "영양관리", "영양"), "보건소 운동·영양관리 프로그램",
     "건강생활 실천을 돕기 위한 운동 및 영양교육 프로그램을 안내합니다.",
     "https://www.saha.go.kr/health/contents.do?mId=0404020000"),
)


def answer_program_alternatives(query: str, current_query: str | None = None) -> dict | None:
    """Explain other known programs and let the next turn choose one."""
    value = compact(query)
    current = compact(current_query if current_query is not None else query)
    asks_other = (
        any(term in current for term in ("다른프로그램", "다른교육", "다른체험", "또다른프로그램",
                                         "그외프로그램", "그밖프로그램", "이외프로그램"))
        or ("프로그램" in current and "또뭐" in current)
    )
    if not asks_other:
        return None

    excluded = {
        key for key, anchors, _title, _description, _url in PROGRAM_CATALOG
        if any(anchor in value for anchor in anchors)
    }
    choices = [item for item in PROGRAM_CATALOG if item[0] not in excluded]
    if not choices:
        choices = list(PROGRAM_CATALOG)
    choices = choices[:4]
    answer = "앞서 안내한 프로그램 외에는 다음과 같은 프로그램도 있습니다.\n\n"
    answer += "\n".join(f"- **{title}**: {description}"
                         for _key, _anchors, title, description, _url in choices)
    answer += "\n\n관심 있는 프로그램 이름을 말씀해 주시면 대상·일정·비용·신청 방법을 자세히 안내해 드릴게요."
    sources = [{"title": f"{title} 공식 안내", "url": url,
                "category": "교육·체험", "department": ""}
               for _key, _anchors, title, _description, url in choices]
    return {
        "answer": answer, "answer_details": "", "sources": sources,
        "is_clarification": False, "degraded": False, "degraded_reason": None,
        "evidence": {"status": "official", "label": "사하구 공식 프로그램 안내",
                     "official_source_count": len(sources), "answer_method": "program_alternatives"},
        "suggested_questions": [f"{title} 자세히 알려줘"
                                for _key, _anchors, title, _description, _url in choices[:3]],
    }


def wants_program_overview(query: str) -> bool:
    value = compact(query)
    if not any(cue in value for cue in PROGRAM_CUES):
        return False
    goal = answer_goal(query)
    if goal in {"method", "eligibility", "cost", "documents", "schedule", "location", "hours", "reference"}:
        return False
    return any(cue in value for cue in OVERVIEW_CUES) or goal in (None, "services")


def _program_label(query: str, page_title: str) -> str:
    matched = find_program_service(query)
    if matched:
        label = str(matched.get("question") or "")
        label = re.split(r"(?:은|는|도)?\s*(?:어떻게|얼마|운영하나요|받을 수|있나요)", label, maxsplit=1)[0]
        label = re.sub(r"\s*(?:수강료|이용료)$", "", label).strip()
        if label:
            return label
    if page_title and compact(page_title) not in {"이용안내", "예약안내", "프로그램안내"}:
        return page_title.strip()
    return "해당 프로그램"


def _clean_lines(body: str) -> list[str]:
    lines = []
    for raw in (body or "").splitlines():
        line = re.sub(r"^[\s•·▪▹▷\-–—]+", "", raw).strip()
        line = re.sub(r"\s+", " ", line)
        for source, target in (("대 상", "대상"), ("수 강 료", "수강료"),
                               ("문 의", "문의"), ("운 영", "운영"), ("구 분", "구분")):
            line = line.replace(source, target)
        if line and line not in lines:
            lines.append(line)
    output = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if (line.endswith((":", "：")) or re.fullmatch(r"(?:이용|교육|신청)?대상", line)) and index + 1 < len(lines):
            following = lines[index + 1]
            if 2 <= len(following) <= 180:
                output.append(line.rstrip(":：") + ": " + following)
                index += 2
                continue
        output.append(line)
        index += 1
    return output


def _informative_lines(lines: list[str], *, detailed: bool = False) -> list[str]:
    fields, floor_activities = [], []
    for line in lines:
        if len(line) < 7 or len(line) > 320:
            continue
        if FIELD_PATTERN.search(line):
            if not re.fullmatch(r"(?:예약안내 및 예약|이용안내|공간안내)", line):
                fields.append(line)
            continue
        # Facility names explain the actual experience; general caution text
        # mentioning "체험관" must not be presented as program content.
        if re.search(r"^(?:[1-4]F|[1-4]층)\b", line, re.IGNORECASE):
            floor_activities.append(line)

    chosen = []
    # What the program actually offers comes before administrative details.
    if floor_activities:
        activity = " / ".join(floor_activities[:4])
        chosen.append("주요 내용: " + activity)
    priorities = (
        r"(?:이용|교육|신청)?대상", r"(?:이용|수강)?료", r"운영시간|이용시간|체험시간",
        r"운영기간", r"예약|신청방법", r"문의|전화번호", r"주소|장소",
    )
    for pattern in priorities:
        line = next((value for value in fields if re.search(pattern, value)), None)
        if line and line not in chosen:
            chosen.append(line)
    if detailed:
        schedules = []
        date_pattern = re.compile(r"^(?:\d{1,2}월(?:~\d{1,2}월)?|연중)$")
        ignored = {"구분", "운영", "이용안내", "공간안내"}
        index = 0
        while index < len(lines) - 1:
            name = lines[index]
            if (name not in ignored and not FIELD_PATTERN.search(name)
                    and not date_pattern.fullmatch(name) and 2 <= len(name) <= 50
                    and date_pattern.fullmatch(lines[index + 1])):
                periods = []
                cursor = index + 1
                while cursor < len(lines) and date_pattern.fullmatch(lines[cursor]):
                    periods.append(lines[cursor])
                    cursor += 1
                schedules.append(f"{name}: {', '.join(periods)}")
                index = cursor
                continue
            index += 1
        if schedules:
            chosen.append("주요 일정: " + " · ".join(schedules[:8]))
    return chosen[:10 if detailed else 6]


def program_overview_answer(query: str, document: dict, body: str) -> dict | None:
    """Summarize only explicit fields from the selected official program page."""
    if not wants_program_overview(query):
        return None
    meta = document.get("metadata") or {}
    detailed = asks_for_detail(query)
    lines = _informative_lines(_clean_lines(body), detailed=detailed)
    if not lines:
        return None
    label = _program_label(query, str(meta.get("title") or ""))
    display_document = {
        **document,
        "metadata": {**meta, "title": f"{label} 이용안내"},
    }
    answer = f"**{label}** 공식 안내입니다.\n\n" + "\n".join(f"- {line}" for line in lines)
    return {
        "answer": answer,
        "answer_details": f"{label}의 공식 안내 원문입니다.\n\n" + "\n".join(
            "> " + line for line in (body or "").splitlines()
        ),
        "is_clarification": False,
        "suggested_questions": [],
        "documents": [display_document],
        "answer_method": "program_overview",
    }
