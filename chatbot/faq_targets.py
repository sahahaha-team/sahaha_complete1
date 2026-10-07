"""Use the supplied question list to select an official page, never its draft answer."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from openpyxl import load_workbook

WORKBOOK = Path(__file__).resolve().parents[1] / "data" / "official_sources" / "사하구 홈페이지_100개 질문.xlsx"


def _normalize(question: str) -> str:
    return re.sub(r"[^가-힣a-z0-9]", "", (question or "").lower())


@lru_cache(maxsize=1)
def _targets() -> list[tuple[str, str]]:
    if not WORKBOOK.is_file():
        return []
    book = load_workbook(WORKBOOK, read_only=True, data_only=True)
    output = []
    try:
        for _number, question, _draft_answer, url in book["예상질문답변"].iter_rows(min_row=2, values_only=True):
            if question and url and str(url).startswith("https://www.saha.go.kr/"):
                output.append((_normalize(str(question)), str(url)))
    finally:
        book.close()
    return output


def match_official_page(question: str) -> str | None:
    normalized = _normalize(question)
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
    # Minor spelling/wording changes are allowed; unrelated topics stay in RAG.
    close = [(SequenceMatcher(None, normalized, candidate).ratio(), url) for candidate, url in targets]
    if not close:
        return None
    score, url = max(close)
    return url if score >= 0.92 else None
