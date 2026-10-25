"""Read a named facility's phone from its registered, current official page."""
from __future__ import annotations
import re
from chatbot.faq_targets import match_official_page, priority_entities
from chatbot.verified_facts import _fresh


def facility_contact(query: str, client) -> dict | None:
    if (not priority_entities(query) or not re.search(r'전화|연락처|번호', query)
            or re.search(r'담당\s*(?:부서|자)|팩스|fax|전화로', query, re.I)):
        return None
    url = match_official_page(query)
    if not url:
        return None
    from database_db.raw_pages import read_raw_pages
    try:
        rows = read_raw_pages(client, 'url,title,content,raw_html,last_checked_at', url=url, limit=1)
    except Exception:
        return None  # The normal evidence path retains lookup/error handling.
    if not rows or not (checked := _fresh(rows[0].get('last_checked_at'))):
        return None
    from chatbot.official_content import official_html_text
    body = official_html_text(rows[0].get('raw_html') or '') or rows[0].get('content') or ''
    phones = set()
    for line in body.splitlines():
        field = re.search(r'(?:^|[▹▷—])\s*(?:문의전화|전화번호|연락처|전화)\s*[:：]\s*(.+)', line)
        if field:
            phones.update(re.findall(r'0\d{1,2}-\d{3,4}-\d{4}(?:\s*~\s*\d{1,4})?', field[1]))
    if len(phones) != 1:
        return None  # Do not choose one library/program from a directory.
    phone = next(iter(phones))
    source = {'title': rows[0].get('title') or '시설 이용안내', 'url': url,
              'checked_at': checked, 'source_type': 'verified_page'}
    return {'answer': f'공식 시설 안내의 **전화번호는 {phone}**입니다.',
            'sources': [source], 'is_clarification': False, 'degraded': False,
            'degraded_reason': None, 'suggested_questions': [],
            'evidence': {'status': 'official', 'label': '공식 시설 연락처 확인됨',
                         'official_source_count': 1, 'answer_method': 'facility_contact'}}
