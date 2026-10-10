"""검색 근거 판정용 순수 함수. 외부 모델이나 데이터베이스가 필요 없다."""

import re
import math
from urllib.parse import urlparse
from chatbot.query_subject import compact, substantive_keywords, SERVICE_NAMES


def is_official_document(doc: dict) -> bool:
    meta = doc.get("metadata") or {}
    if meta.get('source_type') == 'faq_draft' or meta.get('category') == 'official_faq':
        return False  # A linked official URL does not validate a draft's facts.
    url = str(meta.get("url") or "")
    if meta.get("source_type") == "official_report":
        return url.startswith("file://official_reports/")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "saha.go.kr" or host.endswith(".saha.go.kr"))


def is_time_compatible(query: str, doc: dict) -> bool:
    """Historical reports cannot establish today's service rules or 2026 counts."""
    meta = doc.get("metadata") or {}
    requested_years = {int(year) for year in re.findall(r"(20\d{2})\s*년", query or "")}
    content = str(doc.get("content") or "")
    if meta.get("source_type") != "official_report":
        # An explicitly requested year must appear in the factual body,
        # never just in metadata such as today's crawl date.
        if requested_years:
            body_years = {int(year) for year in re.findall(r"(?<!\d)(20\d{2})(?!\d)", content)}
            return requested_years.issubset(body_years)
        return True
    compact = re.sub(r"\s+", "", query or "")
    title = str(meta.get("source_title") or meta.get("title") or "")
    if any(word in compact for word in ("방문자", "검색어", "홈페이지검색", "메뉴별방문")) and "방문자" not in title:
        return False
    if "정보공개청구" in compact and "정보공개청구" not in title:
        return False
    if not any(word in compact for word in (
        "보고서", "분석", "통계", "건수", "방문자", "검색어", "키워드",
        "추이", "처리일수", "순위", "2023", "2024", "2025",
    )):
        return False
    if any(word in compact for word in ("현재", "지금", "오늘", "최신", "올해", "이번달")):
        return False
    period_years = [int(year) for year in re.findall(r"20\d{2}", str(meta.get("data_period") or ""))]
    if requested_years and period_years:
        in_period = all(min(period_years) <= year <= max(period_years) for year in requested_years)
        report_intent = any(word in compact for word in ("보고서", "분석결과", "작성"))
        issued_year = str(meta.get("issued_at") or title)[:4]
        issued_year = issued_year if issued_year.isdigit() else ""
        if not in_period and not (report_intent and requested_years == {int(issued_year or 0)}):
            return False
    return True


def filter_time_compatible(query: str, results: list[dict]) -> list[dict]:
    return [doc for doc in results if is_time_compatible(query, doc)]


def is_listing_document(doc: dict) -> bool:
    meta = doc.get("metadata") or {}
    if meta.get("category") == "staff_directory" or meta.get("source_type") == "official_report":
        return False
    parsed = urlparse(str(meta.get("url") or ""))
    if "/bbs/list.do" in parsed.path:
        return True
    compact = re.sub(r"\s+", "", str(doc.get("content") or ""))
    return "게시판목록" in compact and any(word in compact for word in (
        "검색어를입력", "검색영역", "작성일", "조회", "Page",
    ))


def is_answerable_document(query: str, doc: dict) -> bool:
    """A notice index is evidence for listing requests, not for an office's duty."""
    url = str((doc.get("metadata") or {}).get("url") or "")
    path = urlparse(url).path
    if path.endswith('/main.do') or path in ('/welfare.do', '/reserve', '/reserve/'):
        # Landing-page menus are not a service's instructions.
        return False
    if "/deptIntro/" in url and not any(word in query for word in ("담당", "부서", "업무", "직원", "연락", "전화", "조직")):
        return False
    if not is_listing_document(doc):
        return True
    compact = re.sub(r"\s+", "", query or "")
    if "담당" in compact or "부서" in compact:
        return False
    return any(word in compact for word in ("공지사항", "게시판", "공고목록", "고시공고", "최신소식", "구정소식"))


def unsupported_numbers(answer: str, context: str) -> list[str]:
    """Reject numerical claims that are absent from the exact retrieved text."""
    def tokens(value: str) -> set[str]:
        return {re.sub(r"\D", "", match) for match in
                re.findall(r"(?<!\d)\d[\d,./:-]*", value or "")}
    available = tokens(context)
    # One-digit numbers are often list markers; larger facts must be sourced.
    return sorted(value for value in tokens(answer) if len(value) >= 2 and
                  not any(value in source_number for source_number in available))


def topic_support(doc: dict, keywords: set[str]) -> tuple[bool, set[str]]:
    """Location, generic report words, score alone cannot establish the topic."""
    topics = substantive_keywords(keywords)
    if not topics:
        return False, set()
    meta = doc.get("metadata") or {}
    haystack = compact(f"{meta.get('title', '')} {doc.get('content', '')}")
    matched = {word for word in topics if word in haystack}
    # The health-site scope establishes the institution; its body must still
    # establish the actual service. A health URL alone cannot answer its hours.
    if "보건소" in topics and len(topics) > 1 and urlparse(str(meta.get("url") or "")).path.startswith("/health/"):
        matched.add("보건소")
    # Generic conditions must not outvote the name of the actual service.
    anchors = topics.intersection(SERVICE_NAMES)
    if not anchors.issubset(matched):
        return False, matched
    required = len(topics) if len(topics) <= 2 else math.ceil(len(topics) * 0.75)
    return len(matched) >= required, matched


def is_service_source(query: str, doc: dict, keywords: set[str]) -> bool:
    """A certificate required by another benefit is not its issuance guide."""
    from chatbot.answer_goal import answer_goal
    title = compact(str((doc.get("metadata") or {}).get("title") or ""))
    certificates = {"주민등록등본", "주민등록초본", "건강진단결과서"}.intersection(keywords)
    if certificates and answer_goal(query) in ("method", "cost", "documents") and title:
        return any(name in title for name in certificates) or any(
            word in title for word in ("정부24", "무인민원", "민원실", "제증명", "발급안내"))
    return True


def assess_evidence(
    results: list[dict],
    *,
    keywords: set[str],
    domain_intent: bool,
    min_similarity: float,
) -> dict:
    if not results:
        return {
            "confident": False,
            "status": "insufficient",
            "label": "정확한 자료를 찾지 못함",
            "top_similarity": 0.0,
            "matched_keywords": [],
            "official_source_count": 0,
        }

    # Only documents that establish the substantive topic can lend support.
    official_results = [result for result in results if is_official_document(result)]
    if not official_results:
        return {
            "confident": False,
            "status": "insufficient",
            "label": "정확한 자료를 찾지 못함",
            "top_similarity": 0.0,
            "matched_keywords": [],
            "official_source_count": 0,
        }

    top_similarity = max(
        float(result.get("vector_similarity", result.get("similarity", 0.0)) or 0.0)
        for result in official_results
    )
    supported = []
    for doc in official_results:
        relevant, matched = topic_support(doc, keywords)
        if relevant:
            supported.append((doc, matched))
    matched_keywords = set().union(*(matched for _, matched in supported)) if supported else set()
    official_source_count = len(supported)
    confident = bool(supported)

    if confident:
        status, label = "official", "사하구 공식 자료 확인됨"
    else:
        status, label = "insufficient", "정확한 자료를 찾지 못함"

    return {
        "confident": confident,
        "status": status,
        "label": label,
        "top_similarity": round(top_similarity, 4),
        "matched_keywords": sorted(matched_keywords),
        "official_source_count": official_source_count,
    }


def select_grounded_results(
    results: list[dict],
    *,
    keywords: set[str],
    domain_intent: bool,
    min_similarity: float,
    limit: int = 5,
) -> list[dict]:
    official = [result for result in results if is_official_document(result)]
    if not official:
        return []

    selected, seen = [], set()
    for result in official:
        if not topic_support(result, keywords)[0]:
            continue
        url = (result.get("metadata") or {}).get("url")
        if url in seen:
            continue
        seen.add(url)
        selected.append(result)
        if len(selected) >= limit:
            break
    return selected
