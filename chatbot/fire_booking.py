"""Read the live, registered child fire-experience application guide."""
import re
from bs4 import BeautifulSoup
from chatbot.answer_goal import requested_goals
from chatbot.dialogue_profile import course_audiences, explicit_age, confirmed_audience
from chatbot.query_subject import compact
from chatbot.verified_facts import _fresh

GUIDE = 'https://www.saha.go.kr/reserve/contents.do?mId=1207030000'
FACILITY = 'https://www.saha.go.kr/reserve/contents.do?mId=1207000000'


def section(body, caption):
    active = False
    lines = []
    for line in body.splitlines():
        if line.startswith('#'):
            if active:
                break
            active = compact(line.lstrip('# ')) == caption
        elif active and line.strip():
            lines.append(re.sub(r'^[\s▹▸▶▷]+', '', line).strip())
    return lines


def age_range(value):
    match = re.search(r'(\d{1,2})세이상(\d{1,2})세이하', compact(value))
    return tuple(map(int, match.groups())) if match else None


def fire_booking(query, client):
    text = compact(query)
    named = '소방특화' in text or '들락날락' in text and '소방' in text
    age = explicit_age(query)
    child = confirmed_audience(query) in {'어린이', '아동', '초등학생'} or '어린이' in text or age is not None and age < 18
    if (not ('소방' in text and (named or '체험' in text or child))
            or re.search(r'관리자|책임자|담당|팩스|전화로|전화만', text)
            or 'method' not in requested_goals(query)
            or not set(requested_goals(query)) <= {'method', 'conditions'}):
        return None
    # A generic adult course may have another source. Do not use a child-only
    # programme as proof that no adult programme exists.
    if not named and (confirmed_audience(query) in {'성인', '어른'} or age is not None and age >= 18 or age is None and '성인' in text):
        return None
    from database_db.raw_pages import read_raw_pages
    from chatbot.source_pages import parsed_original
    try:
        rows = read_raw_pages(client, 'url,title,content,raw_html,last_checked_at', urls=[GUIDE, FACILITY])
    except Exception:
        return None
    pages = {r['url']: r for r in rows if _fresh(r.get('last_checked_at'))}
    if GUIDE not in pages or FACILITY not in pages:
        return None
    body, parent = parsed_original(pages[GUIDE]), parsed_original(pages[FACILITY])
    audiences = course_audiences(body.splitlines())
    parent_audiences = course_audiences(parent.splitlines())
    if len(audiences) != 1 or len(parent_audiences) != 1 or '소방특화 들락날락' not in body:
        return None
    sources = [{'url':url, 'title':pages[url].get('title') or '소방특화 들락날락',
                'checked_at':_fresh(pages[url].get('last_checked_at')), 'source_type':'verified_page'}
               for url in (GUIDE, FACILITY)]
    def result(answer, insufficient=False):
        return {'answer':answer,'sources':sources,'is_clarification':False,'suggested_questions':[],
                'degraded':insufficient,'degraded_reason':'booking_scope_unverified' if insufficient else None,
                'evidence':{'status':'insufficient' if insufficient else 'official',
                            'label':'예약 조건 확인 필요' if insufficient else '공식 예약 절차 확인됨',
                            'official_source_count':2,'answer_method':'official_booking'}}
    if not age_range(audiences[0]) or age_range(audiences[0]) != age_range(parent_audiences[0]):
        return result('같은 체험관의 공식 페이지에 이용 대상이 다르게 표시되어 현재 예약 조건 확인이 필요합니다.', True)
    from chatbot.concise_answers import course_scope_result
    scope = course_scope_result(query+' 체험', '신청대상: '+audiences[0])
    if scope:
        if scope.get('is_clarification'):
            return {**scope,'answer_method':'official_booking'}
        return result(scope['answer'],True)
    methods = section(body, '체험예약방법')
    authentication = next((s for s in methods if re.search(r'홈페이지에서\s*신청\(',s) and '본인인증' in s), None)
    opening = next((s for s in methods if re.search(r'매월\s*1일\s*9시',s) and '예약가능' in s),None)
    html = pages[GUIDE].get('raw_html') or ''
    soup = BeautifulSoup(html,'lxml')
    entry = any(a.get_text(' ',strip=True) == '예약신청' and a.get('onclick') == 'fn_agree_proc()'
                for a in soup.find_all(['a','button']))
    consent = bool(re.search(r"function\s+fn_agree_proc\(\)[\s\S]{0,900}location[.]href\s*=\s*['\"]/reserve/fireSpec/list[.]do[?]mId=1207030000['\"]",html)
                   and '개인정보의 수집 이용에 동의하지 않을경우 신청이 불가합니다.' in html)
    if not authentication or not opening or not entry or not consent:
        return None  # Changed/absent controls do not authorize invented steps.
    answer = ('**소방특화 들락날락 예약**\n- 대상: '+audiences[0]+
              '\n- [공식 예약안내 및 예약]('+GUIDE+')에서 개인정보 수집·이용 동의를 확인한 뒤 **예약신청**으로 진행하세요.'+
              '\n- '+authentication+'\n- '+opening)
    minimum = re.search(r'※ 프로그램의 원활한 진행을 위해[^\n]{0,150}\(미달[^\n]{0,70}\)',body)
    if minimum:
        answer += '\n- '+minimum[0]
    if re.search(r'전화번호|연락처',text):
        phone = re.search(r'전화번호\s*[:：]\s*(0\d{1,2}-\d{3,4}-\d{4})', parent)
        if not phone:
            return None
        answer += '\n- 시설 전화: '+phone[1]
    return result(answer) if len(answer) <= 650 else None
