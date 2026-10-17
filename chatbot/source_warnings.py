"""Distinguish a recent crawl from the date of an invitation in its body."""
from datetime import datetime
import re
import json
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def _read_reviews(path: str, modified: int, size: int):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def source_reviews():
    path = Path(__file__).resolve().parents[1] / 'resources' / 'official_source_reviews.json'
    if not path.is_file():
        return []
    stat = path.stat()
    return _read_reviews(str(path), stat.st_mtime_ns, stat.st_size)


def reviewed_source(body: str, metadata: dict) -> tuple[str, dict]:
    """Quarantine reviewed fields while the same outdated text remains.

    This registry stores review decisions, never replacement factual answers.
    A changed official page no longer matching the marker is not quarantined.
    """
    for review in source_reviews():
        if review['url'] == metadata.get('url') and re.search(review['marker'],body):
            blocked = review['unverified_fields']
            from chatbot.structured_answers import field_matches
            safe = '\n'.join(line for line in body.splitlines()
                             if not any(field_matches(field,line) for field in blocked)
                             and not re.search(review.get('unverified_line_pattern') or r'(?!)',line))
            return safe, {**metadata,'unverified_fields':blocked,
                          'source_review_status':review.get('status', 'review_required'),
                          'source_warning':review.get('user_warning') or '공식 원문의 해당 항목은 최신 안내 확인이 필요합니다.'}
    return body, metadata


def reviewed_field_answer(query: str, documents: list[dict], client, keywords: set[str]) -> dict | None:
    """Explain a reviewed blocked field before asking a model to guess it.

    Only relevant originals can establish a warning. An alternative verified
    source with the requested field wins over a quarantined source. Mixed
    requests continue through the ordinary partial-answer path.
    """
    from chatbot.answer_goal import requested_goals
    from chatbot.source_pages import source_document
    from chatbot.evidence_decision import document_decision
    fields = set(requested_goals(query))
    if not fields or 'reference' in fields:
        return None
    reviewed_urls = {review['url'] for review in source_reviews()}
    marked = [doc for doc in documents if (doc.get('metadata') or {}).get('url') in reviewed_urls]
    if not marked:
        return None
    blocked_documents = []
    for doc in marked:
        body, reviewed = source_document(doc, client)
        result = document_decision(query, {**reviewed, 'content': body, '_raw_page': {
            'content': body}}, keywords)
        if not result['relevant']:
            continue
        meta = reviewed.get('metadata') or {}
        blocked = set(meta.get('unverified_fields') or [])
        if fields.issubset(blocked) and meta.get('source_warning'):
            blocked_documents.append(reviewed)
    if not blocked_documents:
        return None
    blocked_urls = {(doc.get('metadata') or {}).get('url') for doc in blocked_documents}
    for doc in documents:
        meta = doc.get('metadata') or {}
        if meta.get('url') in blocked_urls or meta.get('category') == 'staff_directory':
            continue
        # This preflight must not issue one raw-page query per candidate.
        # Unknown originals defer to the ordinary hydrated-source reader.
        result = document_decision(query, doc, keywords)
        if result['relevant'] and ('_raw_page' not in doc and meta.get('source_type') != 'crawled_page'
                                   or fields.issubset(result['matched_fields'])):
            return None
    metadata = blocked_documents[0]['metadata']
    conflict = metadata.get('source_review_status') == 'conflict'
    reason = 'source_conflict' if conflict else 'source_review_required'
    return {'answer': metadata['source_warning'], 'answer_details': '',
            'is_clarification': False, 'degraded': True, 'degraded_reason': reason,
            'evidence_status': 'conflicting' if conflict else 'insufficient',
            'evidence_label': '공식 원문 항목이 서로 다름' if conflict else '공식 원문 항목 확인 필요',
            'evidence_reasons': [reason], 'matched_fields': [],
            'documents': blocked_documents, 'answer_method': 'reviewed_source_field'}


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
