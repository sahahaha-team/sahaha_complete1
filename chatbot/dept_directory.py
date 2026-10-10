"""Department normalization and official contact lookup helpers.

The department/contact map is built from Saha-gu's official staff directory
page and cached in `data/staff_directory.json`.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

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


def _load_directory() -> dict:
    global _DIRECTORY_REFRESH_ATTEMPTED

    if STAFF_DIRECTORY_PATH.exists():
        try:
            data = json.loads(STAFF_DIRECTORY_PATH.read_text(encoding="utf-8"))
            checked_at = datetime.fromisoformat(str(data.get("generated_at", "")).replace("Z", "+00:00"))
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            if checked_at >= datetime.now(timezone.utc) - timedelta(days=7):
                return data
            logger.warning("Staff directory cache is older than seven days; ignoring it")
            return _default_directory()
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
    data = refresh_directory(STAFF_DIRECTORY_PATH)
    from scripts.build_contact_directory import build_contact_directory
    build_contact_directory(data)
    from chatbot.contact_directory import save_contact_payload
    save_contact_payload(data)
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


def department_is_supported(name: str, text: str) -> bool:
    """부서명이 제공된 원문에 실제로 등장하는지 확인한다."""
    normalized = correct_dept(name)
    if not normalized or not text:
        return False
    return _compact(normalized) in _compact(text)


def extract_explicit_department(text: str) -> str:
    """페이지의 담당자/담당부서 표기에서 공식 부서명을 결정적으로 추출한다."""
    if not text:
        return ""
    compact_text = re.sub(r"\s+", " ", text)
    labels = ("담당자", "담당부서", "문의부서", "담당 부서")
    for label in labels:
        start = compact_text.rfind(label)
        if start < 0:
            continue
        nearby = compact_text[start:start + 100]
        for name in sorted(_official_names(), key=len, reverse=True):
            if name and name in nearby:
                return name
    return ""


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


def is_staff_lookup(query: str) -> bool:
    """Recognize an explicit request for the office/person responsible for work."""
    compact = _compact(query)
    return any(word in compact for word in (
        "담당부서", "담당자", "담당하는부서", "어느부서", "무슨부서",
        "부서알려", "부서는", "부서어디", "부서찾", "누가담당", "담당연락처",
        "담당전화", "담당직원", "계장", "팀장", "주무관", "과장", "실장",
    )) or ("담당" in compact and any(word in compact for word in ("부서", "연락", "전화", "누구", "어디")))


def staff_subject_terms(query: str) -> set[str]:
    """Extract actual duties rather than generic 'department/contact' words."""
    text = (query or "").lower()
    text = re.sub(r"(?<![a-z])a\.?i\.?(?![a-z])|인공지능", " 인공지능 ", text)
    # Keep '구청장' as a role, while removing the institution name.
    text = re.sub(r"사하구청(?!장)|사하구|부산광역시", " ", text)
    for word in (
        "알려주세요", "알려줘", "안내해주세요", "해주세요", "담당하는", "담당자",
        "전화번호", "연락처", "담당", "부서", "직원", "업무", "전화", "번호",
        "어디인가요", "누구인가요", "어느", "무슨", "누구", "어디", "문의",
        "궁금", "찾아줘", "가르쳐줘", "알려", "구청",
    ):
        if word == "구청":
            text = re.sub(r"구청(?!장)", " ", text)
        else:
            text = text.replace(word, " ")
    terms = set()
    for token in re.findall(r"[가-힣]{2,}|[a-z]{2,}", text):
        token = re.sub(r"(?:인가요|하나요|있나요|입니다|알려줘|알려주세요)$", "", token)
        if len(token) >= 3 and token[-1] in "은는이가을를의":
            token = token[:-1]
        if len(token) >= 2 and token not in {"있어", "하는", "대한", "에서", "나요", "인가요"}:
            terms.add(token)
    return terms


def _subject_text(value: str) -> str:
    return re.sub(r"(?<![a-z])a\.?i\.?(?![a-z])", "인공지능", (value or "").lower())


def search_staff_directory(query: str, limit: int = 5) -> list[dict]:
    """Find the best matching official staff-directory rows for a query."""
    query_text = (query or "").strip()
    if not query_text:
        return []

    subjects = staff_subject_terms(query_text)
    if not subjects:
        return []

    scored: list[tuple[float, dict]] = []
    for row in _row_records():
        dept = (row.get("department") or "").strip()
        title = (row.get("title") or "").strip()
        duties = (row.get("duties") or "").strip()
        phone = (row.get("phone") or "").strip()
        if not dept and not title and not duties:
            continue

        fields = [_subject_text(value) for value in (dept, title, duties, phone)]
        matched = {term for term in subjects if any(term in field for field in fields)}
        if not matched:
            continue
        score = sum(4 * (term in fields[0]) + 8 * (term in fields[1]) +
                    6 * (term in fields[2]) + (term in fields[3]) for term in matched)
        # A role that explicitly names the work outranks an incidental mention
        # of that work in another service (e.g. a library's AI storytelling).
        score *= len(matched) / len(subjects)

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
                "matched_subjects": sorted(term for term in subjects if term in _subject_text(
                    " ".join(str(row.get(key) or "") for key in ("department", "title", "duties", "phone")))),
                "url": row.get("source_url", "") or row.get("url", "") or STAFF_DIRECTORY_PAGE_URL,
            }
        )
    return results
