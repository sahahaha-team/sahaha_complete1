"""Short answers from verified source text, with intact details kept separately."""
from __future__ import annotations

import re

from chatbot.query_subject import compact, substantive_keywords
from chatbot.question_intent import (
    asks_opening_hours, has_opening_hours, asks_location, has_location_unit, location_source_units,
)
from chatbot.vaccination import vaccination_place_brief, is_vaccination_query
from chatbot.answer_completion import (
    OMISSION, QUALIFICATION, complete_source_units, source_unit_complete, can_continue,
)

MAX_BRIEF_LENGTH = 480


def source_lines(original_answer: str) -> list[str]:
    return [line[2:].strip() for line in original_answer.splitlines() if line.startswith("> ")]


def _passport(query: str, body: str) -> str | None:
    if any(word in query for word in ("기간", "며칠", "소요")) and '유효기간' not in query:
        line = next((line for line in body.splitlines() if re.match(r"여권교부\s*:", line)), None)
        return line if line and len(line) < MAX_BRIEF_LENGTH else None
    if not any(word in query for word in ("서류", "준비", "구비")):
        return None
    if any(word in query for word in ('미성년', '아이', '자녀', '18세미만')):
        lines = [line for line in body.splitlines() if line.startswith(('미성년자의 사진 및 구여권', '친권자(', '미성년자 본인', '미성년자의 2촌'))]
        answer = '\n'.join('- ' + line for line in lines)
        return answer if len(lines) == 2 and len(answer) <= MAX_BRIEF_LENGTH else None
    if any(word in query for word in ("긴급", "관용")):
        return None
    photo = re.search(r"여권용 컬러 사진\s*(\d+매)\(([^)]+)\)", body)
    if not photo or "여권발급신청서 1부" not in body or "신분증" not in body:
        return None
    answer = f"준비물은 **여권발급신청서 1부·신분증·여권용 사진 {photo.group(1)}**입니다."
    answer += "\n\n사진 기준: " + photo.group(2) + "."
    if "유효기간 남은 여권은 지참" in body:
        answer += "\n유효기간이 남은 기존 여권도 지참하세요."
    return answer


def _parking(query: str, body: str) -> str | None:
    if "신고" not in query or any(word in query for word in ("이의", "과태료", "견인", "의견진술")):
        return None
    required = ("신고방법", "안전신문고", "동일한 위치와 방향", "1분 이상", "사진 2장 이상", "촬영시간", "당일 및 익일")
    if not all(word in body for word in required):
        return None
    return ("불법주정차는 **안전신문고 앱**에서 신고하세요.\n\n"
            "- 같은 차량을 같은 위치·방향에서 **1분 이상 간격으로 사진 2장 이상** 촬영하세요.\n"
            "- 위반 위치·차량번호·촬영시각이 보여야 합니다.\n"
            "- **촬영 당일 또는 다음 날**까지 신고하세요. 구역별 운영시간·요건은 원문에서 확인할 수 있어요.")


def _waste(query: str, body: str) -> str | None:
    if not any(word in query for word in ("배출", "버리", "방법", "접수")) or any(word in query for word in ("비용", "수수료", "얼마")):
        return None
    required = ("처리업체에 직접 전화", "문자 접수", "051-266-1170~1", "맑은사하환경", "1:1톡 접수", "무상수거")
    if not all(word in body for word in required):
        return None
    return ("대형폐기물은 **맑은사하환경(051-266-1170~1)**에 전화·문자로 접수하세요. "
            "카카오톡 ‘맑은사하환경’ 1:1 접수도 가능합니다.\n\n"
            "일부 가전제품은 무상수거 대상입니다. **어떤 물품을 버리시는지** 알려주시면 해당 안내를 확인할게요.")


def _source_units(lines: list[str]) -> list[str]:
    return complete_source_units(lines)


def _extract_brief(query: str, lines: list[str], keywords: set[str]) -> str | None:
    location = asks_location(query)
    units = location_source_units(lines) if location else _source_units(lines)
    topics = substantive_keywords(keywords)
    opening_hours = asks_opening_hours(query)
    intent = []
    if any(word in query for word in ("방법", "신청", "접수", "신고")):
        intent = ["방법", "접수", "예약", "신고", "신청"]
    elif any(word in query for word in ("대상", "조건", "자격")):
        intent = ["대상", "조건", "자격"]
    elif any(word in query for word in ("시간", "기간", "며칠")):
        intent = ["시간", "기간", "일정"]
    if intent and any(word in query for word in ("배출", "재활용", "분리수거")):
        intent += ["배출", "분리"]
    # Only complete factual prose/label-value units. Standalone cells such as
    # '58면', '52,000원' cannot be reassigned to another row or condition.
    candidates = []
    for i, unit in enumerate(units):
        label_value = bool(re.search(r"[:：]\s*[가-힣 ]{6,}", unit))
        hours_unit = has_opening_hours(unit)
        place_unit = has_location_unit(unit)
        if (len(unit) < 22 and not label_value and not hours_unit and not place_unit) or len(unit) > 350 or unit.startswith(("Q.", "[…]")):
            continue
        if opening_hours and not hours_unit:
            continue
        if location and not place_unit:
            continue
        if not source_unit_complete(unit):
            continue
        if QUALIFICATION.match(unit):
            continue
        # Omitted context and an unfinished preceding condition cannot be
        # silently detached from an otherwise complete statement.
        if i and (units[i - 1] == OMISSION or can_continue(units[i - 1])):
            continue
        if i + 1 < len(units) and units[i + 1] == OMISSION:
            continue
        value = compact(unit)
        topic_hits = sum(word in value for word in topics)
        goal_hits = sum(word in value for word in intent)
        if intent and not goal_hits and not (opening_hours and hours_unit):
            continue
        if topic_hits or goal_hits or (opening_hours and hours_unit) or (location and place_unit):
            candidates.append((goal_hits * 3 + topic_hits, i))
    if not candidates:
        return None
    for _, start in sorted(candidates, key=lambda item: (-item[0], item[1])):
        chosen = [units[start]]
        # Keep adjacent exceptions whole; never shorten away a condition.
        for unit in units[start + 1:]:
            if QUALIFICATION.match(unit):
                chosen.append(unit)
            else:
                break
        if any(not source_unit_complete(unit) for unit in chosen):
            continue
        answer = "\n".join("- " + line for line in chosen)
        if len(answer) <= MAX_BRIEF_LENGTH:
            return answer
    return None


def scope_question(query: str, body: str) -> dict:
    fields = [("신청 방법", ("신청", "접수", "예약")), ("대상 조건", ("대상", "자격", "조건")),
              ("비용", ("수수료", "요금", "비용")), ("운영시간", ("시간", "일정")),
              ("준비 서류", ("서류", "준비"))]
    choices = [label for label, words in fields if any(word in body for word in words)][:3]
    if not choices:
        choices = ["대상이나 사업명"]
    answer = "안내 범위를 좁혀볼게요. **" + "·".join(choices) + "** 중 어떤 내용을 확인하시겠어요?"
    base = re.sub(r"알려(?:주세요|줘)?|어떻게.*$", "", query).strip().rstrip("?!")
    return {"answer": answer, "answer_details": "", "is_clarification": True,
            "suggested_questions": [f"{base} {choice} 알려줘" for choice in choices],
            "reply_terms": [word for _, words in fields for word in words]}


def concise_source_answer(query: str, original_answer: str, documents: list[dict], keywords: set[str]) -> dict:
    lines = source_lines(original_answer)
    body = "\n".join(lines)
    url = str((documents[0].get("metadata") or {}).get("url") or "") if documents else ""
    answer = vaccination_place_brief(query, url, lines)
    if (asks_location(query) and is_vaccination_query(query)
            and any(mid in url for mid in ('mId=0203020000', 'mId=0203020100')) and not answer):
        return scope_question(query, body)
    if documents and documents[0].get("metadata", {}).get("category") == "staff_directory":
        meta = documents[0]['metadata']
        answer = f"**{meta.get('department', '')}** · **{meta.get('contact', '')}**\n{meta.get('title', '')}"
    if "mId=0104020000" in url:
        answer = _passport(query, body)
    elif "mId=0403080000" in url:
        answer = _parking(query, body)
    elif "대형폐기물" in compact(body) and "대형폐기물" in compact(query):
        answer = _waste(query, body)
    if not answer:
        answer = _extract_brief(query, lines, keywords)
    if not answer:
        return scope_question(query, body)
    meta = (documents[0].get("metadata") or {}) if documents else {}
    if meta.get("source_type") == "official_report":
        answer = f"자료 기준: {meta.get('data_period', '미상')}\n\n" + answer
    return {"answer": answer, "answer_details": original_answer, "is_clarification": False,
            "suggested_questions": []}
