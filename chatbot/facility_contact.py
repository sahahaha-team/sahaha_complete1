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
    from chatbot.dialogue_profile import course_audiences, course_audience_conflict
    if course_audience_conflict(query, course_audiences(body.splitlines())):
        return {'answer':'공식 안내의 이용 대상과 말씀하신 대상이 다릅니다. 해당 대상의 이용 가능 여부와 문의 경로를 이 자료만으로 확정할 수 없습니다.',
                'sources':[{'title':rows[0].get('title') or '시설 이용안내','url':url,'checked_at':checked,'source_type':'verified_page'}],
                'is_clarification':False,'degraded':True,'degraded_reason':'audience_mismatch','suggested_questions':[],
                'evidence':{'status':'insufficient','label':'이용 대상 확인 필요','official_source_count':1,'answer_method':'audience_mismatch'}}
    phones = set()
    inquiry_phones = set()
    for line in body.splitlines():
        field = re.search(r'(?:^|[▹▷—])\s*(?:문의전화|전화번호|연락처|전화)\s*[:：]\s*(.+)', line)
        if field:
            phones.update(re.findall(r'0\d{1,2}-\d{3,4}-\d{4}(?:\s*~\s*\d{1,4})?', field[1]))
        inquiry = re.search(r'(?:^|[▹▷—])\s*문\s*의\s*[:：]\s*(.+)', line)
        if inquiry:
            inquiry_phones.update(re.findall(r'0\d{1,2}-\d{3,4}-\d{4}(?:\s*~\s*\d{1,4})?', inquiry[1]))
    # A programme inquiry number is not a specific branch's direct line.
    # Keep its published role, and leave named local branches to normal search.
    programme_inquiry = bool(not phones and inquiry_phones and re.search(r'프로그램', body)
                             and not re.search(r'(?:괴정|당리|하단|신평|장림|다대|구평|감천)\d?동', query))
    if programme_inquiry:
        phones = inquiry_phones
    if len(phones) != 1:
        return None  # Do not choose one library/program from a directory.
    phone = next(iter(phones))
    source = {'title': rows[0].get('title') or '시설 이용안내', 'url': url,
              'checked_at': checked, 'source_type': 'verified_page'}
    label = '공식 프로그램 안내의 문의 전화번호' if programme_inquiry else '공식 시설 안내의 전화번호'
    return {'answer': f'{label}는 **{phone}**입니다.',
            'sources': [source], 'is_clarification': False, 'degraded': False,
            'degraded_reason': None, 'suggested_questions': [],
            'evidence': {'status': 'official', 'label': '공식 시설 연락처 확인됨',
                         'official_source_count': 1, 'answer_method': 'facility_contact'}}
