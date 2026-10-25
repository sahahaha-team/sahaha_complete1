"""Confirmed scope in an internal search query, separate from requested fields."""
import re

SCOPE_PROFILE = re.compile(r'\(확인대상: [^()]+\)')


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


def child_course_conflict(query: str, body: str) -> bool:
    age = explicit_age(query)
    if (age is None or age >= 14 or not re.search(r'교육|훈련|강좌', query)
            or re.search(r'책임자|관리자|사업주|근로자', request_without_profile(query))):
        return False
    audiences = re.findall(r'(?:이용|교육|참여)?대\s*상\s*[:：]([^\n]+)', body)
    return bool(audiences and any(re.search(r'책임자|관리자|사업주|근로자', value) for value in audiences)
                and not any(re.search(r'어린이|아동|학생|청소년', value) for value in audiences))
