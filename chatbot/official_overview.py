"""Read declared category overviews without substituting a child service."""
import re
from urllib.parse import urljoin, urlparse
from chatbot.faq_targets import find_official_question
from chatbot.verified_facts import _fresh


def official_overview(query: str, client) -> dict | None:
    if not re.search(r'종류|분류|세목|무엇|어떤', query):
        return None
    match = find_official_question(query)
    spec = (match or {}).get('overview')
    if not spec:
        return None
    from database_db.raw_pages import read_raw_pages
    try:
        rows = read_raw_pages(client, 'title,content,raw_html,last_checked_at', url=match['url'], limit=1)
    except Exception:
        return None
    if not rows or not (checked := _fresh(rows[0].get('last_checked_at'))):
        return None
    row = rows[0]
    if spec['kind'] == 'classification':
        from chatbot.official_content import official_html_text
        body = official_html_text(row.get('raw_html') or '') or row.get('content') or ''
        subject = re.escape(spec['subject'])
        units = [line for line in body.splitlines() if re.match(r'^' + subject + r'\s*[-:：]', line)]
        if len(units) != 1 or len(units[0]) > 250:
            return None
        answer = '공식 세금 분류 안내입니다.\n- ' + units[0] + '\n\n세목별 전체 목록은 이 문단만으로 확인할 수 없습니다.'
        partial = True
    elif spec['kind'] == 'navigation':
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(row.get('raw_html') or '', 'lxml')
        root = soup.select_one(spec['root'])
        if root is None:
            return None
        labels = []
        for anchor in root.select(':scope > li > a'):
            target = urljoin(match['url'], anchor.get('href', ''))
            if anchor.get('id') not in spec['menu_ids'] or urlparse(target).hostname != urlparse(match['url']).hostname:
                continue
            label = ' '.join(anchor.get_text(' ', strip=True).split())
            if label and label not in labels:
                labels.append(label)
        if len(labels) != len(spec['menu_ids']):
            return None
        answer = '통합예약의 주요 분야는 **' + ' · '.join(labels) + '**입니다.\n각 프로그램·시설에서 접수 일정과 예약 가능 여부를 확인해 주세요.'
        partial = False
    else:
        return None
    return {'answer': answer, 'sources': [{'title': row.get('title') or match['question'], 'url': match['url'],
             'checked_at': checked, 'source_type': 'verified_page'}], 'is_clarification': False,
            'degraded': partial, 'degraded_reason': 'partial_catalogue' if partial else None,
            'suggested_questions': [], 'evidence': {'status': 'partial' if partial else 'official',
             'label': '공식 분류 일부 확인' if partial else '공식 예약 분야 확인됨',
             'official_source_count': 1, 'answer_method': 'official_overview'}}
