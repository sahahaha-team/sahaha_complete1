"""Read visit-application documents from the current official passport page.

Requirements come from source sections, never a question-to-answer lookup.
The applicant's age and the person visiting the counter are separate facts.
"""
from __future__ import annotations

import re

PASSPORT_URL = 'https://www.saha.go.kr/portal/contents.do?mId=0104020000'


def document_request(query: str) -> bool:
    text = re.sub(r'\s+', '', query or '')
    return ('여권' in text and any(w in text for w in ('준비', '서류', '구비', '챙겨', '가져가', '가져갈'))
            and not any(w in text for w in ('수령', '교부', '긴급', '관용', '외교',
                '기록증명', '사본증명', '실효확인', '정보증명', '국제운전', '온라인', '인터넷')))


def applicant_age(query: str) -> str | None:
    text = re.sub(r'\s+', '', query or '')
    if '18세미만' in text:
        return 'minor'
    age = re.search(r'(?:만)?(\d{1,2})(?:세|살)(?!이상|이하|미만)', text)
    if age:
        return 'minor' if int(age.group(1)) < 18 else 'adult'
    if any(w in text for w in ('미성년', '아이', '자녀')):
        return 'minor'
    if any(w in text for w in ('18세이상', '성인', '어른')):
        return 'adult'
    # 청소년/고등학생 alone do not prove the legal under-18 age condition.
    return None


def applicant_role(query: str) -> str | None:
    text = re.sub(r'\s+', '', query or '')
    if '친족' in text:
        return 'relative'
    if any(w in text for w in ('부모', '친권자', '법정대리인', '아빠', '엄마', '어머니', '아버지', '후견인')):
        return 'parent'
    if any(w in text for w in ('본인', '직접')):
        return 'self'
    return None


def parse_passport_documents(query: str, content: str) -> str | None:
    """Accept both legacy lines and HTML paragraphs; retain role boundaries."""
    body = re.sub(r'^#{1,6}\s+', '', content or '', flags=re.M)
    if not document_request(query):
        return None
    age = applicant_age(query)
    new = re.search(r'(?:^|\n)신규발급\s+(?:일반여권\s+)?(.*?)\s*긴급여권', body, re.S)
    renewal = re.search(r'(?:^|\n)재발급\s+(.*?)\s*여권발급 등에 관한 수수료', body, re.S)
    if not new or age is None:
        return None
    common = new.group(1).split('만18세 미만 미성년자의 여권 신청', 1)[0]
    if age == 'adult' and '재발급' in query:
        if not renewal:
            return None
        common = renewal.group(1)
    form = re.search(r'여권발급신청서\s*\d+\s*부', common)
    photo = re.search(r'여권용\s*컬러\s*사진\s*\d+\s*매\s*\([^)]*\)', common)
    if not form or not photo or '신분증' not in common:
        return None
    form_value = ' '.join(form.group().split())
    photo_value = ' '.join(photo.group().split())
    # The source says 2 photos for Saha visits. Label the authority explicitly;
    # the national passport guide's minimum (1 photo) is a different source.
    lines = ['**사하구청 방문 신청 안내 기준**', '- ' + form_value + ', ' + photo_value]
    if age == 'adult':
        if any(w in query for w in ('대리', '대신')):
            return None  # Adult proxy eligibility is not proved by this section.
        lines.append('- 신청자 신분증')
        if '재발급' in query:
            if not re.search(r'유효기간\s*남은\s*여권은\s*지참', common):
                return None
            lines.append('- 유효기간이 남은 기존 여권도 지참하세요.')
            lines.append('분실·훼손·정보 변경 등 재발급 사유별 추가 서류는 별도 확인이 필요합니다.')
    else:
        role = applicant_role(query)
        if role is None:
            return None
        section = re.search(r'만\s*18세\s*미만\s*미성년자의\s*여권\s*신청\s+(.*?)\s*긴급여권', body, re.S)
        if not section:
            return None
        markers = [
            ('parent', r'친권자\s*\(혹은\s*법정대리인\)\s*신청\s*시\s*[:：]'),
            ('self', r'미성년자\s*본인\s*신청(?:서|\s*시)\s*[:：]'),
            ('relative', r'미성년자의\s*2촌\s*이내\s*친족\s*\(만\s*18세\s*이상\)\s*신청\s*시\s*[:：]'),
        ]
        matches = [(name, re.search(pattern, section.group(1))) for name, pattern in markers]
        if any(match is None for _, match in matches):
            return None  # Do not treat missing role headings as a parent's list.
        bounds = {name: (match.end(), matches[i+1][1].start() if i+1 < len(matches) else len(section.group(1)))
                  for i, (name, match) in enumerate(matches)}
        start, end = bounds[role]
        required = ' '.join(section.group(1)[start:end].split())
        if not required or '법정대리인 동의서' not in required:
            return None
        role_label = {'parent': '부모·법정대리인', 'self': '미성년자 본인', 'relative': '만 18세 이상 2촌 이내 친족'}[role]
        lines[0] = '**만 18세 미만 · ' + role_label + ' 방문 신청 기준**'
        lines.append('- ' + required)
        if not re.search(r'구여권\s*\(유효기간\s*만료\s*전\s*여권\)', body):
            return None
        lines.append('- 유효기간이 남은 기존 여권도 지참하세요.')
    answer = '\n'.join(lines)
    return answer if len(answer) <= 480 else None


def answer_passport_documents(query: str, client) -> dict | None:
    if not document_request(query):
        return None
    from database_db.raw_pages import read_raw_pages
    from chatbot.verified_facts import _fresh
    from chatbot.official_content import official_html_text
    try:
        rows = read_raw_pages(client, 'content,raw_html,last_checked_at', url=PASSPORT_URL, limit=1)
    except Exception:
        rows = []
    row = rows[0] if rows else {}
    checked = _fresh(row.get('last_checked_at'))
    body = official_html_text(row.get('raw_html') or '') or row.get('content') or ''
    answer = parse_passport_documents(query, body) if checked else None
    if not answer:
        return {'answer': '현재 공식 여권 안내에서 해당 신청자의 준비 서류를 완전히 확인하지 못했습니다. 신청 유형과 대리 신청 조건은 여권 창구에서 확인해 주세요.',
                'sources': [], 'verified': False, 'answer_method': 'passport_documents',
                'verification_label': '여권 신청 서류 확인 필요'}
    return {'answer': answer, 'answer_details': '\n'.join('> ' + line for line in body.splitlines()),
            'sources': [{'title': '여권발급안내', 'url': PASSPORT_URL, 'category': '전자민원',
                         'service_type': '민원', 'source_type': 'verified_page', 'checked_at': checked}],
            'verified': True, 'answer_method': 'passport_documents',
            'verification_label': '공식 여권 신청 서류 확인됨'}
