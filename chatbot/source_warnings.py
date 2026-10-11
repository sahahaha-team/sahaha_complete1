"""Distinguish a recent crawl from the date of an invitation in its body."""
from datetime import datetime
import re
import json
from pathlib import Path


def reviewed_source(body: str, metadata: dict) -> tuple[str, dict]:
    """Quarantine reviewed fields while the same outdated text remains.

    This registry stores review decisions, never replacement factual answers.
    A changed official page no longer matching the marker is not quarantined.
    """
    path = Path(__file__).resolve().parents[1] / 'resources' / 'official_source_reviews.json'
    reviews = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []
    for review in reviews:
        if review['url'] == metadata.get('url') and re.search(review['marker'],body):
            blocked = review['unverified_fields']
            from chatbot.structured_answers import field_matches
            safe = '\n'.join(line for line in body.splitlines()
                             if not any(field_matches(field,line) for field in blocked))
            return safe, {**metadata,'unverified_fields':blocked,
                          'source_warning':review.get('user_warning') or '공식 원문의 해당 항목은 최신 안내 확인이 필요합니다.'}
    return body, metadata


def dated_invitation_warning(body: str, *, year: int | None = None) -> str:
    current_year = year or datetime.now().year
    dates = []
    for line in (body or '').splitlines():
        # Insurance reference months, enactment dates and historical purposes
        # are not recruitment announcements. An invitation must be explicit.
        if re.search(r'참여.*바랍|신청.*바랍|모집.*(?:안내|공고)|실시하니',line):
            dates += [int(y) for y in re.findall(r'(20\d{2})\s*년',line)]
    old = [y for y in dates if y < current_year]
    if not old:
        return ''
    return f'원문에 {max(old)}년 모집 안내가 포함되어 있어, 현재 모집 여부·일정은 별도 확인이 필요합니다.'
