"""A single registered national guide supplements the same local benefit."""
import re
from datetime import datetime
from bs4 import BeautifulSoup
from chatbot.answer_goal import requested_goals
from chatbot.dialogue_profile import explicit_age
from chatbot.query_subject import compact
from chatbot.verified_facts import _fresh

POLICY = 'https://www.mohw.go.kr/menu.es?mid=a10710030100'
LOCAL = 'https://www.saha.go.kr/portal/contents.do?mId=0504020200'


def policy_content(html):
    root = BeautifulSoup(html or '', 'lxml').select_one('#contents_body')
    return root.get_text('\n', strip=True) if root else ''


def policy_fields(html, year):
    root = BeautifulSoup(html or '', 'lxml').select_one('#contents_body')
    if not root:
        return None
    lines = [' '.join(str(c).strip() for c in node.contents if isinstance(c,str)).strip()
             for node in root.find_all(['li','p'])]
    target = [s for s in lines if re.fullmatch(r'18세 이상의 장애인연금법상 중증장애인 중 본인과 배우자의 소득과 재산을 합산한 금액\(소득인정액\)이 선정기준액 이하인 사람',s)]
    age = [s for s in lines if s.startswith('신청일이 속한 월 당시,') and '18세 이상' in s and '월 말일까지' in s]
    criteria = [s.lstrip('* ') for s in lines if re.match(r'[* ]*선정기준액\('+str(year)+r'년\)\s*:',s)]
    if len(target)!=1 or len(age)!=1 or len(criteria)!=1:
        return None
    amounts = re.search(r'배우자가 없는 중증장애인\s*(\d+)만원,\s*배우자가 있는 중증장애인\s*(\d+)만원',criteria[0])
    return (target[0],age[0],criteria[0],amounts.groups()) if amounts else None


def disability_policy(query, client):
    text = compact(query)
    year = datetime.now().year
    years = set(map(int,re.findall(r'(?<!\d)(20\d{2})년',text)))
    if years and years != {year} or re.search(r'작년|지난해|과거|예전|내년',text):
        return None
    if ('장애인연금' not in text or set(requested_goals(query))!={'eligibility'}
            or explicit_age(query) is not None
            or re.search(r'공무원|직역|학교|학생|재학|장애수당|아동수당|활동지원|급여|지급액|외국|국적|장애등급',text)):
        return None  # No personal entitlement or another programme from a basic guide.
    from database_db.raw_pages import read_raw_pages
    from chatbot.source_pages import parsed_original
    try:
        rows=read_raw_pages(client,'url,title,content,raw_html,last_checked_at',urls=[POLICY,LOCAL])
    except Exception:
        return None
    pages={r['url']:r for r in rows if _fresh(r.get('last_checked_at'))}
    if POLICY not in pages or LOCAL not in pages:
        return None
    fields=policy_fields(pages[POLICY].get('raw_html') or '',datetime.now().year)
    if not fields:
        return None
    target,age,criteria,amounts=fields
    local=parsed_original(pages[LOCAL])
    own=local.split('#### 장애수당',1)[0]
    local_amounts=re.search(str(year)+r'년 선정기준액\s*\n단독가구\s*:\s*(\d+)만원\s*\n부부가구\s*:\s*(\d+)만원',own)
    if not local_amounts or local_amounts.groups()!=amounts:
        return None  # Inconsistent guides must not silently supply a new amount.
    answer=('**장애인연금 기본 신청 자격**\n- '+target+'\n- 연령 기준: '+age+
            '\n- '+criteria+'\n실제 수급 여부는 소득·재산 조사와 장애정도 심사 후 결정됩니다.')
    return {'answer':answer,'sources':[{'url':u,'title':pages[u].get('title') or '장애인연금 공식 안내',
            'checked_at':_fresh(pages[u].get('last_checked_at')),'source_type':'verified_page'} for u in (POLICY,LOCAL)],
            'is_clarification':False,'degraded':False,'degraded_reason':None,'suggested_questions':[],
            'evidence':{'status':'official','label':'같은 제도의 중앙·구청 안내 확인됨','official_source_count':2,'answer_method':'official_policy_supplement'}}
