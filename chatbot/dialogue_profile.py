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
