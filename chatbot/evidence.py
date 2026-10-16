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
    # A quoted old rule followed by "지금도 그대로?" asks for today's rule.
    # Explicit historical statistics/comparisons still retain their years.
    if (re.search(r'지금|현재|아직', query or '') and re.search(r'라던|이전|예전|그대로', query or '')
            and not re.search(r'통계|건수|보고서|비교|추이', query or '')):
        requested_years = set()
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
    if parsed.path.endswith('/contents.do') and re.search(
            r'(?:진료내용|지원내용|신청방법|검진수수료|진료대상).{0,150}[가-힣]{4}', compact):
        return False  # A content page may embed a notice list below real service facts.
    return "게시판목록" in compact and any(word in compact for word in (
        "검색어를입력", "검색영역", "작성일", "조회", "Page",
    ))


def is_answerable_document(query: str, doc: dict) -> bool:
    """A notice index is evidence for listing requests, not for an office's duty."""
    url = str((doc.get("metadata") or {}).get("url") or "")
    path = urlparse(url).path
    request = compact(query)
    # '민원실' exists in both portals. Explicitly asking about the district
    # office cannot establish the health center's location/clinical hours.
    if '/health/' in path and ('구청민원실' in request or
            ('구청' in request and '민원실' in request)) and '보건소' not in request:
        return False
    title = compact(str((doc.get('metadata') or {}).get('title') or ''))
    primary_heading = next((compact(line.lstrip('# ')) for line in str(doc.get('content') or '').splitlines()
                            if line.startswith('## ')),title)
    from chatbot.question_intent import asks_opening_hours, asks_location
    general_health_hours = ('보건소' in request and (asks_opening_hours(query) or asks_location(query))
        and not re.search(r'검사|검진|접종|백신|임신|임산부|금연|치매|센터|진료실|물리치료|보건증|건강진단',request))
    if general_health_hours and re.search(
            r'임신|임산부|예비부모|예방접종|백신|금연|치매|센터|진료실|물리치료|영양플러스|방문건강|검진|의료기관', title+' '+primary_heading):
        return False  # A program's venue/hours do not establish the institution's address/hours.
    if general_health_hours and '/health/' not in path and '보건소' not in title:
        return False  # A district-office counter is not the health-center clinic.
    for district, facility in re.findall(r'([가-힣]{2,6}구)\s*(보건소|청)', query):
        if district != '사하구' and compact(district+facility) not in compact(str(doc.get('content') or '')):
            return False
    if '민원실' in request and '무인' not in request and '무인민원' in primary_heading:
        return False
    if '민원실' in request and '여권' not in request and '여권' in title:
        return False
    if '통합예약' in request and '/reserve/' not in path:
        return False
    if path.endswith('/main.do') or path in ('/welfare.do', '/reserve', '/reserve/'):
        # Landing-page menus are not a service's instructions.
        return False
    if "/deptIntro/" in url and not any(word in query for word in ("담당", "부서", "업무", "직원", "연락", "전화", "조직")):
        return False
    if not is_listing_document(doc):
        return True
    requested = re.sub(r"\s+", "", query or "")
    if "담당" in requested or "부서" in requested:
        return False
    return any(word in requested for word in ("공지사항", "게시판", "공고목록", "고시공고", "최신소식", "구정소식"))


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
    if '법정감염병' in topics and len(set(re.findall(r'제[1-4]급감염병', haystack))) >= 2:
        matched.add('법정감염병')  # Statutory classes establish the subject without that exact title.
    if '옥외대피' in topics and '외부공간' in haystack:
        matched.add('옥외대피')
    if '옥외' in topics and '외부공간' in haystack:
        matched.add('옥외')
    if '민간임대주택' in topics and '민간임대' in haystack and '주택' in haystack:
        matched.add('민간임대주택')
    # Breadcrumbs are removed from originals. An actual online civil-service
    # instruction can establish 전자민원 without repeating the menu's name.
    body = compact(str(doc.get('content') or ''))
    if '전자민원' in topics and (re.search(
            r'(?:온라인|인터넷).{0,100}(?:민원|서류).{0,80}(?:상담|접수|발급|신청)', body)
            or re.search(r'(?:민원|서류).{0,80}(?:상담|접수|발급|신청).{0,100}(?:온라인|인터넷)', body)):
        matched.add('전자민원')
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
    anchors = set(keywords).intersection(SERVICE_NAMES) - {'보건소','디지털','컴퓨터','냉장고','세탁기','구직','구인','전자민원'}
    body_text = str(doc.get('content') or '')
    if '소방' in anchors:
        from chatbot.query_subject import service_term_present
        if not service_term_present('소방', str((doc.get('metadata') or {}).get('title') or '') + '\n' + body_text):
            return False
    if '주민등록증' in anchors:
        # Identity-card issuance cannot borrow its procedure from a passport
        # or kiosk page merely listing the card as a required document.
        if '주민등록증' not in title:
            return False
        if re.search(r'재발급|분실|잃어|훼손', query) and '재발급' not in title:
            return False
        if re.search(r'처음|신규', query) and '재발급' in title:
            return False
    # A specific named program/facility cannot be replaced by a different
    # one merely because both pages explain 신청 or contain the same amount.
    requested_entities = re.findall(r'([가-힣A-Za-z0-9]{2,20})\s*(센터|도서관|체육관|지원금|보조금|장려금|수당|보험|클리닉)', query)
    owners = [line.lstrip('# ') for line in body_text.splitlines() if line.startswith('#')]
    owners += [line.split(' — ', 1)[0] for line in body_text.splitlines() if ' — ' in line]
    owners += [line.strip() for line in body_text.splitlines() if re.fullmatch(
        r'[^:：,.。]{2,40}(?:센터|도서관|체육관|지원금|보조금|장려금|수당|보험|클리닉)(?:\s*(?:운영|안내))?', line.strip())]
    source_text = compact(title + ' ' + ' '.join(owners))
    for name, kind in requested_entities:
        name = re.sub(r'^(?:사하구청|사하구|부산광역시)', '', name)
        # A generic issuing counter is incidental to a certificate's papers.
        # Do not require a 주민센터 heading in the district's issuance guide;
        # this does not establish any particular centre's address or hours.
        if (kind == '센터' and name in {'주민', '동주민', '행정복지', '동행정복지'}
                and answer_goal(query) == 'documents'
                and anchors.intersection({'인감증명', '본인서명사실확인서',
                                          '주민등록등본', '주민등록초본'})):
            continue
        if name and compact(name + kind) not in source_text:
            return False
    if (answer_goal(query) == 'necessity' and re.search(r'서류|행정|기관|제출', query)
            and (re.search(r'임산부|임신|출산|미숙아|선천성|영유아', title) or '/health/' in str((doc.get('metadata') or {}).get('url') or ''))
            and not re.search(r'임산부|임신|출산|산모|아기|미숙아|선천성|영유아|보건|건강|검진|검사|접종|치매', query)):
        return False  # A generic document-sharing question is not maternity aid.
    if '검사' in query and not re.search(r'접종|백신',query) and '접종' in title and '검사' not in title:
        return False
    if '암환자' in anchors and '소아암' in title and not re.search(r'소아|아동|아이|어린|미성년',query):
        return False
    headings = [compact(line.lstrip('# ').split('※',1)[0]) for line in body_text.splitlines()
                if line.startswith('#')]
    headings += [compact(line.split(' — ',1)[0]) for line in body_text.splitlines() if ' — ' in line]
    if not headings:
        headings = [compact(line) for line in body_text.splitlines() if re.fullmatch(
            r'[^:：,·]{2,35}(?:안내|사업|제도|지원|관리|신청|헌장|방법)(?:\[[^\]]+\])?',line.strip())]
    if anchors and not any(a in title or any(a in h for h in headings) for a in anchors):
        # Some dedicated pages have generic titles such as 설치안내. Their
        # opening complete fact must name the subject and requested field;
        # a passing mention elsewhere in a benefit page is still insufficient.
        from chatbot.answer_goal import requested_goals
        from chatbot.structured_answers import field_matches
        opening = body_text[:450].splitlines()
        fields = requested_goals(query)
        # A dedicated facility's generic 이용안내 can declare its purpose in
        # 공간안내. This is the same facility's rooms, not another program's
        # incidental mention elsewhere in a multi-service page.
        space = re.search(r'^#{2,6}\s*(?:공간안내|시설안내)\s*$([\s\S]*?)(?=^#{2,6}\s|\Z)',body_text,re.M)
        dedicated_space = (title in {'이용안내','시설이용안내','체험관이용안내'} and space is not None
            and any(all(a in compact(unit) for a in anchors) and re.search(r'교육센터|교육관|체험관',unit)
                    for unit in space.group(1).splitlines())
            and not any(any(n in h for n in SERVICE_NAMES if n not in anchors and n not in {'보건소','구청'})
                        for h in headings))
        if not dedicated_space and (not fields or not any(all(a in compact(unit) for a in anchors) and
                any(field_matches(field, unit, query) for field in fields) for unit in opening)):
            return False
    if '자전거' in compact(query) and re.search(r'대여|빌리|빌릴|렌탈', query):
        body = compact(str(doc.get('content') or ''))
        if not re.search(r'자전거.{0,80}(?:대여|대출|빌리)|(?:대여|대출).{0,80}자전거', body):
            return False
    certificates = {"주민등록등본", "주민등록초본", "건강진단결과서"}.intersection(keywords)
    if certificates and answer_goal(query) in ("method", "cost", "documents") and title:
        return any(name in title for name in certificates) or any(
            word in title for word in ("정부24", "무인민원", "민원실", "제증명", "발급안내", "수수료면제"))
    return True


def assess_evidence(
    results: list[dict],
    *,
    keywords: set[str],
    domain_intent: bool,
    min_similarity: float,
    query: str | None = None,
) -> dict:
    if query is not None:
        from chatbot.evidence_decision import assess_documents
        return assess_documents(query, results, keywords, min_similarity=min_similarity)
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
    query: str | None = None,
) -> list[dict]:
    official = [result for result in results if is_official_document(result)]
    if not official:
        return []

    selected, seen = [], set()
    for result in official:
        from chatbot.evidence_decision import document_decision
        relevant = (document_decision(query, result, keywords, min_similarity=min_similarity)['relevant']
                    if query is not None else topic_support(result, keywords)[0])
        if not relevant:
            continue
        url = (result.get("metadata") or {}).get("url")
        if url in seen:
            continue
        seen.add(url)
        selected.append(result)
        if len(selected) >= limit:
            break
    return selected
