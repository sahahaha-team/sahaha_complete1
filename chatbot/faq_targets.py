"""Use the supplied question list to select an official page, never its draft answer."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from openpyxl import load_workbook
from chatbot.question_intent import asks_opening_hours, asks_location
from chatbot.query_subject import fallback_keywords
from chatbot.vaccination import vaccine_place_page
from chatbot.official_faq import OfficialFAQIndex, PRIORITY_SERVICE_PATH

WORKBOOK = Path(__file__).resolve().parents[1] / "data" / "official_sources" / "사하구 홈페이지_100개 질문.xlsx"


@lru_cache(maxsize=1)
def _question_indexes() -> tuple[OfficialFAQIndex, OfficialFAQIndex]:
    return OfficialFAQIndex(), OfficialFAQIndex(PRIORITY_SERVICE_PATH)


def find_official_question(question: str) -> dict | None:
    """FAQ similarity is a navigation hint, never proof of a draft answer."""
    matches = [index.find_best(question, min_score=0.88) for index in _question_indexes()]
    return max((match for match in matches if match), key=lambda match: match['score'], default=None)


def _normalize(question: str) -> str:
    return re.sub(r"[^가-힣a-z0-9]", "", (question or "").lower())


@lru_cache(maxsize=1)
def _targets() -> list[tuple[str, str]]:
    # Committed JSON keeps the official question routes usable on a new PC.
    output = [(_normalize(str(item['question'])), str(item['url']))
              for index in _question_indexes() for item in index.items
              if str(item.get('url', '')).startswith('https://www.saha.go.kr/')]
    if not WORKBOOK.is_file():
        return output
    book = load_workbook(WORKBOOK, read_only=True, data_only=True)
    try:
        for _number, question, _draft_answer, url in book["예상질문답변"].iter_rows(min_row=2, values_only=True):
            if question and url and str(url).startswith("https://www.saha.go.kr/"):
                output.append((_normalize(str(question)), str(url)))
    finally:
        book.close()
    return output


def match_official_page(question: str) -> str | None:
    normalized = _normalize(question)
    vaccine_url = vaccine_place_page(question)
    if vaccine_url:
        return vaccine_url
    from chatbot.official_faq import required_faq_ids
    if required_faq_ids(question) == {1, 2}:
        return 'https://www.saha.go.kr/portal/contents.do?mId=0604050000'
    if asks_location(question) and fallback_keywords(question) == {'보건소'}:
        return 'https://www.saha.go.kr/health/contents.do?mId=0103000000'
    if asks_location(question) and fallback_keywords(question) == {'구청'}:
        return 'https://www.saha.go.kr/portal/contents.do?mId=0604050000'
    # The health-center directions page also contains its general clinical
    # hours. Do not substitute a village health center or a service's hours.
    if ('보건소' in normalized and asks_opening_hours(question)
            and not any(word in normalized for word in (
                '마을건강', '건강생활지원', '보건지소', '치매', '금연', '접종',
                '검사', '보건증', '건강진단', '검진', '모자보건', '구강', '물리치료',
            ))):
        return 'https://www.saha.go.kr/health/contents.do?mId=0103000000'
    # Confirmed service + question goal selects its verified guide directly.
    # Conversational qualifiers like '성인이야/처음이야' must not let an
    # unrelated adult vaccination page crowd the passport guide out of top 5.
    if '여권' in normalized and any(word in normalized for word in ('준비', '서류', '구비', '사진', '발급기간', '기간은', '며칠', '소요')):
        return 'https://www.saha.go.kr/portal/contents.do?mId=0104020000'
    if any(word in normalized for word in ('불법주차', '불법주정차')) and '신고' in normalized:
        return 'https://www.saha.go.kr/portal/contents.do?mId=0403080000'
    if '대형폐기물' in normalized and any(word in normalized for word in ('배출', '방법', '접수', '수수료')):
        return 'https://www.saha.go.kr/portal/contents.do?mId=0405050103'
    if len(normalized) < 7:
        return None
    targets = _targets()
    for candidate, url in targets:
        if normalized == candidate:
            return url
    match = find_official_question(question)
    if match and str(match.get('url', '')).startswith('https://www.saha.go.kr/'):
        return match['url']
    # Minor spelling/wording changes are allowed; unrelated topics stay in RAG.
    close = [(SequenceMatcher(None, normalized, candidate).ratio(), url) for candidate, url in targets]
    if not close:
        return None
    score, url = max(close)
    return url if score >= 0.92 else None
