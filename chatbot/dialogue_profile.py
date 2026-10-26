"""Confirmed scope in an internal search query, separate from requested fields."""
import re

SCOPE_PROFILE = re.compile(r'\(확인대상: [^()]+\)')
COURSE = re.compile(r'교육|훈련|강좌|체험')
DEMOGRAPHIC = {'성인', '어른', '어린이', '아동', '초등학생', '미성년자'}


def request_without_profile(query: str) -> str:
    return SCOPE_PROFILE.sub('', query)


def confirmed_profile(query: str) -> str:
    match = SCOPE_PROFILE.search(query)
    return match.group() if match else ''


def confirmed_audience(query: str) -> str:
    profile = confirmed_profile(query)
    return profile[len('(확인대상: '):-1] if profile else ''


def explicit_age(query: str) -> int | None:
    request = request_without_profile(query)
    match = re.search(r'(?<!\d)(?:만\s*)?(\d{1,2})\s*(?:세|살)(?!\s*(?:이상|이하|미만))', request)
    return int(match[1]) if match else None


def replace_demographic(query: str) -> str:
    """A new participant age/type replaces only the old demographic slot."""
    query = SCOPE_PROFILE.sub(lambda m: '' if m.group()[len('(확인대상: '):-1] in DEMOGRAPHIC else m.group(), query)
    query = re.sub(r'(?:만\s*)?\d{1,2}\s*(?:세|살)(?!\s*(?:이상|이하|미만))', '', query)
    return re.sub(r'성인|어른|어린이|초등학생|미성년자?', '', query).strip()


def course_audiences(units: list[str]) -> list[str]:
    values = []
    audience_heading = False
    for unit in units:
        if unit.startswith('#'):
            audience_heading = bool(re.fullmatch(r'(?:신청|이용|교육|참여)대상(?:및인원)?', re.sub(r'[\s#]', '', unit)))
            continue
        unit = re.sub(r'^[\s▹▸▶▷-]+', '', unit)
        match = re.match(r'(?:(?:이용|교육|참여|신청)\s*)?대\s*상\s*[:：]\s*(.+)', unit)
        if match:
            values.append(re.split(r'[▹▸▶▷]', match[1], maxsplit=1)[0].strip())
        elif audience_heading and re.search(r'어린이|성인|학생|주민|구민|세\s*이상', unit):
            values.append(unit)
        audience_heading = False
    return values


def course_audience_conflict(query: str, values: list[str]) -> bool:
    """Check the participant against owned audience fields, never menu words."""
    if not COURSE.search(query) or not values:
        return False
    age = explicit_age(query)
    scope = confirmed_audience(query)
    adult = age is None and (scope in {'성인','어른'} or bool(re.search(r'성인|어른', request_without_profile(query))))
    child = age is None and scope in {'어린이','아동','초등학생','미성년자'}
    def conflict(value):
        text = re.sub(r'\s+', '', value)
        bounds = re.search(r'(\d{1,2})세이상(?:[~∼～-])?(\d{1,2})세이하', text)
        if bounds:
            low, high = map(int, bounds.groups())
            return (not low <= age <= high) if age is not None else (adult and high < 18) or (child and low >= 18)
        if re.search(r'어린이|아동|초등학생', text) and not re.search(r'성인|누구나|전연령', text):
            return adult or (age is not None and age >= 18)
        if re.search(r'성인|만?18세이상', text) and not re.search(r'어린이|아동|누구나|전연령', text):
            return child or (age is not None and age < 18)
        return False
    return all(conflict(value) for value in values)


def child_course_conflict(query: str, body: str) -> bool:
    age = explicit_age(query)
    if (age is None or age >= 14 or not re.search(r'교육|훈련|강좌', query)
            or re.search(r'책임자|관리자|사업주|근로자', request_without_profile(query))):
        return False
    audiences = re.findall(r'(?:이용|교육|참여)?대\s*상\s*[:：]([^\n]+)', body)
    return bool(audiences and any(re.search(r'책임자|관리자|사업주|근로자', value) for value in audiences)
                and not any(re.search(r'어린이|아동|학생|청소년', value) for value in audiences))
