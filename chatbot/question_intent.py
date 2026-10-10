"""Recognize the information requested, independently of the facility name."""
from __future__ import annotations

import re
from chatbot.answer_completion import complete_source_units, source_unit_complete, starts_label

_OPENING = re.compile(
    r"(?:운영|진료|업무|근무|이용|개관|개장|접수|상담|점심)시간|"
    r"몇시|여는시간|여는지|열어|열어요|여나요|닫는시간|닫아|닫나요|"
    r"문(?:을)?(?:여는|열|닫)|오픈시간|마감시간"
)
_DURATION = re.compile(r"소요시간|시간(?:이)?걸|얼마나걸|처리기간|발급기간|며칠")
_HOURS_LABEL = re.compile(r"(?:운영|진료|업무|근무|이용|개관|개장|접수|상담|점심)\s*시간")
_CLOCK = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3])(?:\s*:\s*[0-5]\d|\s*시)")
_DAYS = re.compile(r"평일|주말|공휴일|[월화수목금토일]요일|월[~∼～\-]금")
_PLACE_FIELD = re.compile(
    r"^(?:(?:접종|신청|접수|발급|배출|진료|검사|상담|교육|행사|설치)\s*)?"
    r"(?:장\s*소|위\s*치|주\s*소)\s*[:：]\s*(\S.*)$"
)
_PLACE_ENTITY = re.compile(
    r"보건소|구청|행정복지센터|주민센터|청사|의료기관|병원|의원|민원실|상담실|"
    r"접종실|도서관|문화회관|복지관|센터|온라인|홈페이지|[가-힣0-9]+(?:로|길)\s*\d+"
)


def asks_location(query: str) -> bool:
    # Do not concatenate '공장 소음' into a spurious '장소' request.
    return bool(re.search(
        r"어디|(?:장소|위치|주소)(?:\s|[?？!]|$|[은는이가을를와과도]|알려)|"
        r"(?:하는|할|받는|맞는|접종|발급|신청)\s*(?:곳|데)", query or '',
    ))


def has_location_unit(text: str) -> bool:
    """A historical mention of a hospital is not a service location."""
    text = text or ""
    if not source_unit_complete(text) or not _PLACE_ENTITY.search(text):
        return False
    if re.search(r"과거|접종했|접종받았|접종력|접종한\s*경우|접종\s*불필요", text):
        return False
    field = _PLACE_FIELD.match(text)
    if field:
        value = field.group(1)
        return bool(_PLACE_ENTITY.search(value)) and not bool(re.search(r'(?:대상자?|조건|자격)$', value))
    return bool(re.search(
        r"(?:에|에는)\s*(?:위치|있습니다)|(?:에서|으로)\s*(?:방문|신청|접수|발급|접종|상담)|"
        r"에서.{0,35}(?:가능|받으|맞으)", text,
    ))


def location_source_units(lines: list[str]) -> list[str]:
    """Pair only explicit place row headers with a recognizable place value."""
    units = complete_source_units(lines)
    paired = []
    i = 0
    while i < len(units):
        unit = units[i]
        if (i + 1 < len(units) and re.fullmatch(
                r"(?:(?:접종|신청|접수|발급|진료|검사|상담)\s*)?(?:장\s*소|위\s*치|주\s*소)", unit)
                and not starts_label(units[i + 1])
                and not (i + 2 < len(units) and _PLACE_ENTITY.search(units[i + 2])
                         and not source_unit_complete(units[i + 2]))
                and has_location_unit(unit + ': ' + units[i + 1])):
            paired.append(unit + ': ' + units[i + 1])
            i += 2
        else:
            paired.append(unit)
            i += 1
    return paired


def has_location(text: str) -> bool:
    return any(has_location_unit(unit) for unit in location_source_units((text or '').splitlines()))


def location_subject(query: str) -> str:
    if not asks_location(query):
        return query
    return re.sub(
        r"장소|위치|주소|어디(?:에서|서|에|로)?|(?:하는|할|받는|맞는)\s*(?:곳|데)|"
        r"(?<=접종)\s*곳|(?<=발급)\s*곳|(?<=신청)\s*곳|맞아(?:요)?|맞을|하는", " ", query,
    )


def asks_opening_hours(query: str) -> bool:
    text = re.sub(r"\s+", "", query or "")
    return not _DURATION.search(text) and bool(_OPENING.search(text))


def has_opening_hours(text: str) -> bool:
    """A matching topic or the word '시간' alone does not answer a time query."""
    text = text or ""
    clocks = _CLOCK.findall(text)
    if _HOURS_LABEL.search(text):
        return bool(clocks) or bool(re.search(r"휴무|휴관|운영하지|진료하지", text))
    return bool(_DAYS.search(text)) and (len(clocks) >= 2 or bool(re.search(r"휴무|휴관", text)))


def opening_hours_subject(query: str) -> str:
    """Keep the facility/service; time wording belongs to the answer intent."""
    if not asks_opening_hours(query):
        return query
    return re.sub(
        r"(?:운영|진료|업무|근무|이용|개관|개장|접수|상담|점심)?\s*시간|"
        r"몇\s*시(?:에|부터|까지)?|여는|열어(?:요)?|여나요|닫는|닫아(?:요)?|닫나요|"
        r"오픈|마감|언제|해\??$", " ", query,
    )
