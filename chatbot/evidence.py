"""검색 근거 판정용 순수 함수. 외부 모델이나 데이터베이스가 필요 없다."""


def is_official_document(doc: dict) -> bool:
    meta = doc.get("metadata") or {}
    url = str(meta.get("url") or "").lower()
    return url.startswith("file://") or "saha.go.kr" in url


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
    matched_keywords: set[str] = set()
    official_source_count = 0
    bm25_supported = False
    for result in official_results:
        official_source_count += 1
        meta = result.get("metadata") or {}
        haystack = f"{meta.get('title', '')} {result.get('content', '')}"
        matched_keywords.update(keyword for keyword in keywords if keyword in haystack)
        bm25_supported = bm25_supported or float(result.get("bm25_score", 0.0) or 0.0) > 0

    lexical_supported = bool(matched_keywords) or bm25_supported
    semantic_supported = top_similarity >= min_similarity
    confident = official_source_count > 0 and (
        lexical_supported or (domain_intent and semantic_supported)
    )

    if confident and lexical_supported:
        status, label = "official", "사하구 공식 자료 확인됨"
    elif confident:
        status, label = "supported", "관련 공식 자료 확인됨"
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

    lexical = []
    for result in official:
        meta = result.get("metadata") or {}
        haystack = f"{meta.get('title', '')} {result.get('content', '')}"
        if any(keyword in haystack for keyword in keywords) or float(result.get("bm25_score", 0.0) or 0.0) > 0:
            lexical.append(result)

    if lexical:
        return lexical[:limit]
    if domain_intent:
        return [
            result for result in official
            if float(result.get("vector_similarity", result.get("similarity", 0.0)) or 0.0)
            >= min_similarity
        ][:limit]
    return []
