"""Shared source eligibility and requested-field coverage.

Retrieval scores identify candidates, not correctness probabilities. A relevant
source can still lack a requested field; only complete verified originals may
take a direct-answer shortcut. No DB or model calls are performed here.
"""
from __future__ import annotations

from functools import lru_cache

FIELD_LABELS = {
    'hours': '운영시간', 'location': '장소', 'cost': '비용',
    'documents': '구비서류', 'method': '신청·이용 방법', 'schedule': '기간·일정',
    'eligibility': '이용·지원 대상', 'conditions': '조건·예외',
    'services': '서비스 내용', 'definition': '제도 설명',
    'specifications': '규격', 'precautions': '주의사항', 'necessity': '필요 여부',
    'reference': '공식 확인 경로',
}


@lru_cache(maxsize=512)
def _coverage(query: str, body: str, title: str, keywords: tuple[str, ...]):
    from chatbot.answer_goal import requested_goals
    from chatbot.structured_answers import scoped_units, field_matches
    from chatbot.source_scope import normalize_plain_source
    from chatbot.source_hierarchy import heading_path
    fields = tuple(requested_goals(query))
    normalized = normalize_plain_source(body, title)
    units = scoped_units(query, normalized, set(keywords))
    matched = []
    for field in fields:
        if field == 'reference':
            # A menu or misleading title alone cannot establish a reference.
            if body.strip(): matched.append(field)
        elif any(not unit.startswith('#') and
                 field_matches(field, unit, query, heading_path(units, i))
                 for i, unit in enumerate(units)):
            matched.append(field)
    return fields, tuple(matched)


def source_body(document: dict) -> str:
    row = document.get('_raw_page')
    if row is not None:
        from chatbot.official_content import official_html_text
        return official_html_text(row.get('raw_html') or '') or row.get('content') or ''
    return str(document.get('content') or '')


def document_decision(query: str, document: dict, keywords: set[str], *, min_similarity: float = .45) -> dict:
    from chatbot.evidence import (is_official_document, is_time_compatible,
                                  is_answerable_document, is_service_source, topic_support)
    metadata = document.get('metadata') or {}
    body = source_body(document)
    checked = {**document, 'content': body}
    reasons = []
    if not is_official_document(checked): reasons.append('untrusted_source')
    if not is_time_compatible(query, checked): reasons.append('time_mismatch')
    if not is_answerable_document(query, checked): reasons.append('wrong_source_kind')
    if not is_service_source(query, checked, keywords): reasons.append('wrong_service')
    topic_document = checked
    if document.get('_raw_page') is not None or metadata.get('source_type') == 'crawled_page':
        # A title left over from an earlier crawl cannot lend a missing topic
        # to a newly changed factual body. Institution-only queries retain the
        # checked institution title, since an address need not repeat its name.
        topic_document = {**checked, 'metadata': {'url': metadata.get('url'),
            'title': metadata.get('title') if keywords.issubset({'구청', '보건소'}) else ''}}
    lexical, matched = topic_support(topic_document, keywords)
    if not lexical: reasons.append('topic_not_established')
    raw_similarity = float(document.get('vector_similarity', 0) or 0)
    fields, covered = _coverage(query, body, str(metadata.get('title') or ''), tuple(sorted(keywords)))
    missing = tuple(field for field in fields if field not in covered)
    relevant = not reasons
    # Absence of a field is not absence of a related source. The source reader
    # and constrained model can still resolve a field or return partial facts.
    state = ('supported' if fields and not missing else 'partial' if covered else 'needs_evidence') if relevant else 'unavailable'
    return {'relevant': relevant, 'decision': state, 'reasons': reasons,
            'requested_fields': list(fields), 'matched_fields': list(covered),
            'missing_fields': list(missing), 'matched_keywords': sorted(matched),
            'vector_candidate': raw_similarity >= min_similarity,
            'vector_similarity': raw_similarity}


def assess_documents(query: str, documents: list[dict], keywords: set[str], *, min_similarity: float = .45) -> dict:
    rows = [(doc, document_decision(query, doc, keywords, min_similarity=min_similarity)) for doc in documents]
    eligible = [(doc, result) for doc, result in rows if result['relevant']]
    best = max((result for _, result in eligible),
               key=lambda result: (result['decision'] == 'supported', len(result['matched_fields'])), default=None)
    from chatbot.answer_goal import requested_goals
    fields = list(requested_goals(query))
    reasons = sorted({reason for _, result in rows for reason in result['reasons']})
    if not eligible: reasons.append('no_relevant_source')
    elif best and best['missing_fields']: reasons = ['missing_requested_fields']
    else: reasons = []
    state = best['decision'] if best else 'unavailable'
    return {'confident': bool(eligible), 'decision': state, 'reasons': reasons,
            'status': 'official' if state == 'supported' else 'partial' if state == 'partial' else 'insufficient',
            'label': '공식 자료 확인됨' if state == 'supported' else '요청 항목 일부 확인' if state == 'partial' else '요청 항목 확인 필요' if eligible else '충분한 공식 근거를 찾지 못함',
            'top_similarity': round(max((r['vector_similarity'] for _, r in rows), default=0), 4),
            'matched_keywords': sorted({word for _, r in eligible for word in r['matched_keywords']}),
            'official_source_count': len({(doc.get('metadata') or {}).get('url') for doc, _ in eligible}),
            'requested_fields': fields, 'matched_fields': best['matched_fields'] if best else [],
            'missing_fields': best['missing_fields'] if best else fields}


def unavailable_answer(reason: str = 'insufficient') -> dict:
    messages = {
        'retrieval_error': '공식 자료를 조회하는 중 문제가 생겨 지금은 충분한 근거를 확인하지 못했습니다. 잠시 후 다시 질문해 주세요.',
        'stale_evidence': '관련 자료는 있지만 최신 내용으로 확인할 수 없어 확정해서 안내하기 어렵습니다.',
        'insufficient': '확인한 사하구청 공식 자료에서 질문에 답할 충분한 근거를 찾지 못했습니다.',
    }
    return {'answer': messages.get(reason, messages['insufficient']), 'sources': [],
            'is_clarification': False, 'degraded': True, 'degraded_reason': reason,
            'evidence': {'status': 'insufficient', 'label': '공식 근거 확인 필요',
                         'decision': 'unavailable', 'reasons': [reason], 'official_source_count': 0},
            'suggested_questions': []}
