"""Department normalization and official contact lookup helpers.

The department/contact map is built from Saha-gu's official staff directory
page and cached in `data/staff_directory.json`.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from crawler.staff_directory import OUTPUT_PATH as STAFF_DIRECTORY_PATH, refresh_directory

logger = logging.getLogger(__name__)

REP_PHONE = "051-220-4000"
STAFF_DIRECTORY_PAGE_URL = "https://www.saha.go.kr/portal/staff/list.do?mId=0604030000"

# A few high-value aliases keep common user wording aligned with the official
# staff directory naming.
MANUAL_DEPT_ALIASES = {
    "기획과": "기획실",
    "홍보과": "기획실",
    "전산과": "정보통신과",
    "ai담당부서": "기획실",
}

_DIRECTORY_REFRESH_ATTEMPTED = False


def _compact(value: str) -> str:
    return re.sub(r"[\s\-/_.()\[\]{}]", "", value or "").strip().lower()


def _default_directory() -> dict:
    return {
        "source_url": "",
        "generated_at": "",
        "rows": [],
        "departments": [],
    }


@lru_cache(maxsize=1)
def _load_directory() -> dict:
    global _DIRECTORY_REFRESH_ATTEMPTED

    if STAFF_DIRECTORY_PATH.exists():
        try:
            return json.loads(STAFF_DIRECTORY_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read staff directory cache: %s", exc)

    if not _DIRECTORY_REFRESH_ATTEMPTED:
        _DIRECTORY_REFRESH_ATTEMPTED = True
        try:
            return refresh_directory(STAFF_DIRECTORY_PATH)
        except Exception as exc:
            logger.warning("Failed to refresh staff directory cache: %s", exc)

    return _default_directory()


def refresh_staff_directory() -> dict:
    """Force a fresh crawl from the official staff directory page."""
    _load_directory.cache_clear()
    data = refresh_directory(STAFF_DIRECTORY_PATH)
    return data


def _department_records() -> list[dict]:
    data = _load_directory()
    records = data.get("departments") or []
    return [r for r in records if isinstance(r, dict)]


def _row_records() -> list[dict]:
    data = _load_directory()
    records = data.get("rows") or []
    return [r for r in records if isinstance(r, dict)]


def _official_names() -> list[str]:
    return [r.get("name", "").strip() for r in _department_records() if r.get("name")]


def _alias_lookup() -> dict[str, str]:
    lookup = { _compact(alias): target for alias, target in MANUAL_DEPT_ALIASES.items() }
    for name in _official_names():
        lookup[_compact(name)] = name
    return lookup


def _best_official_match(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        return ""

    compact = _compact(cleaned)
    alias_lookup = _alias_lookup()
    if compact in alias_lookup:
        return alias_lookup[compact]

    official_names = _official_names()
    exact = [n for n in official_names if _compact(n) == compact]
    if exact:
        return exact[0]

    contains = [n for n in official_names if compact and (compact in _compact(n) or _compact(n) in compact)]
    if contains:
        contains.sort(key=lambda item: (len(item), item))
        return contains[0]

    if cleaned.endswith(("과", "실", "팀", "동", "센터", "소")):
        prefix = cleaned[:-1]
        prefix_matches = [n for n in official_names if _compact(n).startswith(_compact(prefix))]
        if prefix_matches:
            prefix_matches.sort(key=lambda item: (len(item), item))
            return prefix_matches[0]

    return cleaned


def correct_dept(name: str) -> str:
    """Normalize a department name to the official staff directory label."""
    return _best_official_match(name)


def normalize_dept_names(text: str) -> str:
    """Replace department aliases inside free-form text."""
    if not text:
        return text

    result = text
    for alias, target in sorted(MANUAL_DEPT_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        result = result.replace(alias, target)
    return result


def get_contact(dept: str) -> str:
    """Return the official contact number for a department, or the rep line."""
    if not dept:
        return REP_PHONE

    dept_name = correct_dept(dept)
    for record in _department_records():
        if record.get("name") == dept_name:
            phone = (record.get("phone") or "").strip()
            return phone or REP_PHONE

    return REP_PHONE


def search_staff_directory(query: str, limit: int = 5) -> list[dict]:
    """Find the best matching official staff-directory rows for a query."""
    query_text = (query or "").strip()
    if not query_text:
        return []

    q_compact = _compact(query_text)
    q_lower = query_text.lower()
    expanded_terms = set()
    expanded_query = q_lower
    if "ai" in q_lower or "인공지능" in query_text:
        expanded_terms.update({"ai", "인공지능", "디지털", "정보화", "전산"})
    if "연락처" in query_text or "전화" in query_text:
        expanded_terms.update({"전화번호", "전화", "연락처", "담당", "부서"})
    tokens = {
        token
        for token in re.split(r"[\s,./]+", query_text)
        if len(token.strip()) >= 2
    }
    expanded_terms.update(token.lower() for token in tokens)

    scored: list[tuple[float, dict]] = []
    for row in _row_records():
        dept = (row.get("department") or "").strip()
        title = (row.get("title") or "").strip()
        duties = (row.get("duties") or "").strip()
        phone = (row.get("phone") or "").strip()
        if not dept and not title and not duties:
            continue

        haystack = " ".join([dept, title, duties, phone]).lower()
        score = 0.0

        if q_compact and q_compact in _compact(dept):
            score += 5.0
        if q_compact and q_compact in _compact(title):
            score += 4.0
        if q_compact and q_compact in _compact(duties):
            score += 3.0
        if q_lower in haystack or expanded_query in haystack:
            score += 2.5
        for term in expanded_terms:
            if term and term in haystack:
                if term in {"ai", "인공지능", "디지털", "정보화", "전산"}:
                    score += 2.0
                else:
                    score += 0.6
        if "담당부서" in q_lower and "담당" in haystack:
            score += 1.0

        for token in tokens:
            token_lower = token.lower()
            if token_lower in haystack:
                score += 0.8

        if score > 0:
            scored.append((score, row))

    scored.sort(key=lambda item: (-item[0], item[1].get("department", ""), item[1].get("title", "")))

    results = []
    for score, row in scored[:limit]:
        dept = correct_dept(row.get("department", "") or "")
        results.append(
            {
                "score": score,
                "department": dept,
                "title": row.get("title", ""),
                "contact": row.get("phone", "") or get_contact(dept),
                "duties": row.get("duties", ""),
                "url": row.get("source_url", "") or row.get("url", "") or STAFF_DIRECTORY_PAGE_URL,
            }
        )
    return results
