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


def asks_eligibility(query: str) -> bool:
    return bool(re.search(r'대상|조건|자격|누가|몇\s*살|어떤\s*(?:사람|차량)|선정|수급\s*(?:기준|조건|자격)', query or ''))


def asks_tax_liability(query: str) -> bool:
    text = query or ''
    return (bool(re.search(r'재산세|자동차세|취득세|주민세|등록면허세|납세', text))
            and bool(re.search(r'기준일|날짜|누가|내나요|납세의무', text)))


def requested_field_score(query: str, heading: str) -> int:
    """Prefer the requested source field; eligibility is not an application form."""
    text = re.sub(r'\s+', '', heading or '')
    if re.search(r'불이익|불이행|안\s*내면|내지\s*않|납부하지\s*않', query):
        return 4 if re.search(r'불이익|압류|영치|공매|가산', text) else 0
    if re.search(r'감면|감경', query):
        return 4 if re.search(r'감경|감면|자진납부', text) else 0
    if re.search(r'기간.*아니|연중|언제든|언제나', query):
        return 3 if re.search(r'운영목적|운영기간|처리방법|365|연중', text) else 0
    if re.search(r'언제.*공시|공시.*언제', query):
        return -3 if re.search(r'의견제출|이의신청', text) else 7 if re.search(r'공시(?:일|기준일)|결정.*공시', text) else 0
    if asks_location(query) and re.search(r'창구|배치', query):
        return 8 if re.search(r'배치도|배치설명', text) else 2 if '창구번호' in text else 0
    if asks_location(query):
        return 5 if re.search(r'위치|장소|주소|이용안내', text) else 1 if re.search(r'기관|센터', text) else 0
    if asks_tax_liability(query):
        return int(bool(re.search(r'납세의무|과세기준', text)))
    if re.search(r'몇\s*(?:살|세)|연령|나이', query):
        return 5 if re.search(r'연령|생후|\d+세|\d+개월', text) else 2 if '선정기준' in text else 0
    if asks_eligibility(query):
        if re.search(r'중지결정|조건불이행|지급중단|환수|수급탈락', text):
            return 1 if re.search(r'중지|불이행|중단|환수|탈락', query) else -1
        return int(bool(re.search(r'대상|선정기준|자격|조건', text)))
    patterns = []
    if re.search(r'서류|준비|구비', query): patterns += [r'구비|서류|준비물|신규발급']
    if re.search(r'얼마|비용|수수료|요금|금액', query): patterns += [r'지원내용|지원금액|수수료|요금|진료비|수강료']
    if re.search(r'언제|시간|기간|며칠|자주', query): patterns += [r'시간|기간|주기|시기|생후|개월|접종실|청소안내']
    if re.search(r'어떻게|방법|버리|배출|신청|신고', query): patterns += [r'방법|절차|요령|배출|신청|접수']
    if re.search(r'무엇|뭐|종류|어떤.*(?:사업|서비스|진료)|있나요|수\s*있', query): patterns += [r'내용|개요|안내|운영|대상|지원']
    if re.search(r'온라인|인터넷', query): patterns += [r'온라인|인터넷|정부24|국민신문고|조회|발급']
    if re.search(r'감면|감경', query): patterns += [r'감경|감면|자진납부']
    if re.search(r'언제.*공시|공시.*언제', query): patterns += [r'공시(?:일|기준일)|결정.*공시']
    if asks_location(query): patterns += [r'위치|장소|오시는|기관|센터|배치도|이용안내']
    if re.search(r'어떻게.*(?:행동|해야)|행동|대처', query): patterns += [r'행동요령|대처|할것|하지말|자제|실외활동']
    if re.search(r'무엇.*왜|무엇이고|왜.*관리', query): patterns += [r'성질|유해|위해|정의|이란']
    return sum(bool(re.search(pattern, text)) for pattern in patterns)


def asks_navigation(query: str) -> bool:
    return bool(re.search(r'어디(?:에서|서)?\s*(?:확인|볼|찾)', query or ''))


def asks_location(query: str) -> bool:
    if asks_navigation(query):
        return False
    # Do not concatenate '공장 소음' into a spurious '장소' request.
    return bool(re.search(
        r"어디|(?:장소|위치|주소)(?:\s|[?？!]|$|[은는이가을를]|알려)|"
        r"(?:하는|할|받는|받을|맞는|접종|발급|신청)\s*(?:곳|데)", query or '',
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
        r"장소|위치|주소|어디(?:에서|서|에|로)?|(?:하는|할|받는|받을|맞는)\s*(?:곳|데)|"
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
