"""Answer requests for official pages/maps using verified navigation metadata."""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import unquote, urlparse

from chatbot.answer_goal import answer_goal
from chatbot.evidence import is_official_document, is_answerable_document, topic_support


def safe_official_link(url: str) -> bool:
    try:
        parsed = urlparse(url or '')
    except ValueError:
        return False
    host = (parsed.hostname or '').lower()
    return (parsed.scheme == 'https' and (host == 'saha.go.kr' or host.endswith('.saha.go.kr'))
            and not parsed.username and not parsed.password
            and not re.search(r'[\s<>"()]', url))


def link_label(text: str) -> str:
    return re.sub(r'[\[\]<>*`\\]', '', text or '').strip()[:100]


def reference_answer(query: str, document: dict, body: str, keywords: set[str],
                     original: str = '') -> dict | None:
    """Explain where to check rather than treating a slogan as a factual answer.

    Map-only pages also answer general/location queries through their verified
    map link. They cannot establish current route lengths or rules.
    """
    meta = document.get('metadata') or {}
    title = str(meta.get('title') or '')
    goal = answer_goal(query)
    map_page = any(word in title.replace(' ', '') for word in ('현황도', '안내지도', '위치도'))
    detail = (('통행 규칙',r'통행\s*규칙|통행\s*(?:가능|금지)|자전거만'),
              ('전용도로 지정 여부',r'전용\s*여부'),
              ('총 길이',r'총\s*길이|몇\s*(?:km|킬로)'))
    missing_detail = next((label for label,pattern in detail if map_page and re.search(pattern,query,re.I)),None)
    if goal != 'reference' and not (map_page and goal in (None, 'location')) and not missing_detail:
        return None
    url = str(meta.get('url') or '')
    if (not safe_official_link(url) or not is_official_document(document)
            or not is_answerable_document(query, document)
            or not topic_support({'content': body, 'metadata': {'url': url}}, keywords)[0]):
        return None
    label = link_label(title) or '공식 안내'
    if missing_detail:
        from chatbot.concise_answers import _source_units
        from chatbot.structured_answers import field_matches
        if any(field_matches(goal,u,query) and re.search(r'통행|전용|길이|km|킬로',u,re.I)
               for u in _source_units(body.splitlines())):
            return None  # Actual rule facts should go through the source reader.
        return {'answer': f'확인한 공식 원문에서는 **{missing_detail}**에 관한 확정 근거가 부족합니다. '
                f'[{label}]({url})는 위치 확인용으로 참고해 주세요.',
                'answer_details':original,'is_clarification':False,'suggested_questions':[],
                'documents':[document],'answer_method':'official_reference','degraded':True}
    answer = f'사하구청 [{label}]({url})에서 확인할 수 있습니다.'
    attachments = [a for a in meta.get('attachments') or [] if isinstance(a, dict)
                   and safe_official_link(str(a.get('url') or ''))]
    attachments.sort(key=lambda a: not any(w in str(a.get('name') or '') for w in ('현황', '지도', '자세히')))
    if attachments:
        attachment = attachments[0]
        file_url = attachment['url']
        name = link_label(str(attachment.get('name') or '첨부자료')) or '첨부자료'
        is_pdf = urlparse(file_url).path.lower().endswith('.pdf')
        file_label = name + (' (PDF)' if is_pdf and 'PDF' not in name.upper() else '')
        answer += f'\n\n[{file_label}]({file_url})를 열어 상세 자료를 보세요.'
        # A filename year is not a publication date. State only what is known.
        filename = unquote(urlparse(file_url).path.rsplit('/', 1)[-1])
        years = re.findall(r'(?<!\d)(20\d{2})(?!\d)', filename)
        if years and max(map(int, years)) < datetime.now().year:
            answer += f'\n파일명에 **{max(years)}**이 포함된 자료이므로 최신 변경 사항은 별도 확인이 필요합니다.'
    if len(answer) > 480:
        # Very long file URLs stay clickable in source cards; do not truncate
        # an address or remove the warning about a dated source.
        answer = f'사하구청 공식 「{label}」 페이지에서 확인할 수 있습니다. 아래 출처의 첨부자료를 열어 상세 내용을 보세요.'
        if attachments and years and max(map(int, years)) < datetime.now().year:
            answer += f'\n파일명에 **{max(years)}**이 포함된 자료이므로 최신 변경 사항은 별도 확인이 필요합니다.'
    return {'answer': answer, 'answer_details': original,
            'is_clarification': False, 'suggested_questions': [],
            'documents': [document], 'answer_method': 'official_reference'}
