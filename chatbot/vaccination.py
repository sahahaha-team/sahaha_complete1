"""Keep vaccination programs and their official place fields separate."""
from __future__ import annotations

import re
from chatbot.question_intent import asks_location, location_source_units, has_location_unit

ADULT_VACCINE_URL = 'https://www.saha.go.kr/health/contents.do?mId=0203020000'
_KINDS = {
    '인플루엔자': r'인플루엔자|독감',
    '폐렴구균': r'폐렴구균|폐렴\s*(?:백신|접종)|ppsv23|pcv\d*',
    'B형간염': r'b형\s*간염',
    'A형간염': r'a형\s*간염',
    '장티푸스': r'장티푸스',
    '파상풍': r'파상풍|디프테리아|백일해|\btd(?:ap)?\b',
    '코로나': r'코로나|covid',
    'HPV': r'사람유두종|자궁경부암|\bhpv\b',
    '대상포진': r'대상포진',
    'BCG': r'\bbcg\b|결핵',
    '홍역': r'홍역|\bmmr\b',
    '일본뇌염': r'일본뇌염',
    '수두': r'수두',
    '로타': r'로타',
    '황열': r'황열',
    '콜레라': r'콜레라',
    'RSV': r'\brsv\b|호흡기세포융합',
}
_SUPPORTED = {'인플루엔자', '폐렴구균', 'B형간염', 'A형간염', '장티푸스', '파상풍'}


def vaccine_kind(query: str) -> str | None:
    kinds = [kind for kind, pattern in _KINDS.items() if re.search(pattern, query or '', re.I)]
    return kinds[0] if len(kinds) == 1 else None


def is_vaccination_query(query: str) -> bool:
    return bool(re.search(r'접종|백신|예방주사', query or '')) or bool(
        vaccine_kind(query) and re.search(r'맞', query or ''))


def needs_vaccine_kind(query: str) -> bool:
    if re.search(r'어린이|아이|아기|영유아|국가예방접종|국가필수', query or ''):
        return False  # The general children's program has its own institution list.
    return (asks_location(query) and is_vaccination_query(query) and not vaccine_kind(query)
            and '예방접종실' not in re.sub(r'\s+', '', query))


def vaccine_place_page(query: str) -> str | None:
    if not (asks_location(query) and is_vaccination_query(query) and vaccine_kind(query) in _SUPPORTED):
        return None
    # Children's programs and other pneumococcal products have their own evidence.
    if re.search(r'어린이|아이|아기|영유아|신생아|pcv|13가|15가|20가', query, re.I):
        return None
    return ADULT_VACCINE_URL


def vaccination_section(query: str, url: str, body: str) -> str | None:
    if not (asks_location(query) and is_vaccination_query(query)
            and any(mid in url for mid in ('mId=0203020000', 'mId=0203020100'))):
        return None
    kind = vaccine_kind(query)
    if kind not in _SUPPORTED:
        return ''
    if re.search(r'어린이|아이|아기|영유아|신생아|pcv|13가|15가|20가', query, re.I):
        return ''
    if kind == '폐렴구균':
        ages = [int(age) for age in re.findall(r'(\d{1,3})\s*세', query)]
        if any(age < 65 for age in ages) or re.search(r'65\s*세\s*미만', query):
            return ''
        start, end = '65세 이상 어르신 폐렴구균 예방접종', '인플루엔자 예방접종'
    elif kind == '인플루엔자':
        if re.search(r'임산부|임신부|임신', query):
            return ''  # This page does not describe the pregnancy program.
        start, end = '인플루엔자 예방접종', '해외여행자 예방접종'
    else:
        start, end = '유료 및 성인 예방접종 안내', '65세 이상 어르신 폐렴구균 예방접종'
    lines = body.splitlines()
    # Exact headings avoid matching navigation links and mentions in another row.
    starts = [i for i, line in enumerate(lines) if line.strip() == start]
    if not starts:
        return ''
    begin = starts[-1]
    finish = next((i for i in range(begin + 1, len(lines)) if lines[i].strip() == end), None)
    if finish is None:
        return ''
    section = '\n'.join(lines[begin:finish])
    if kind not in ('폐렴구균', '인플루엔자') and kind.lower() not in re.sub(r'\s+', '', section).lower():
        return ''
    return section


def vaccination_place_brief(query: str, url: str, lines: list[str]) -> str | None:
    """Quote the program's place first, retaining scope and site restrictions."""
    if not (asks_location(query) and is_vaccination_query(query)
            and any(mid in url for mid in ('mId=0203020000', 'mId=0203020100'))):
        return None
    kind = vaccine_kind(query)
    units = location_source_units(lines)
    places = [unit for unit in units if has_location_unit(unit)]
    if len(places) != 1:
        return None
    if kind == '폐렴구균':
        heading = '65세 이상 어르신 폐렴구균 예방접종'
    elif kind == '인플루엔자':
        heading = '인플루엔자 예방접종'
    else:
        heading = '유료 및 성인 예방접종 안내'
    if heading not in lines:
        return None
    answer = f'**{heading}**\n\n- {places[0]}'
    if kind == '인플루엔자':
        target = next((unit for unit in units if unit.startswith('대상 :')), None)
        notice = next((unit for unit in units if unit.startswith('※ 지정의료기관')), None)
        if (not target or not notice or '매년' not in notice or '공고 예정' not in notice
                or '※현재 보건소에서는 직접 주사 안됨' not in '\n'.join(lines)):
            return None
        answer += '\n- ' + target + '\n- ※현재 보건소에서는 직접 주사 안됨\n- ' + notice
    return answer if len(answer) <= 480 else None
