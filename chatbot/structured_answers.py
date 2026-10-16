"""Answer explicit fields from intact, scoped official HTML units.

This is a source reader, not an FAQ answer table. It uses the current page's
heading hierarchy and labels; names, values and conditions are copied together.
The model remains the fallback when the requested field cannot be resolved.
"""
from __future__ import annotations

import re
from chatbot.answer_goal import answer_goal, requested_goals
from chatbot.answer_completion import source_unit_complete, QUALIFICATION
from chatbot.concise_answers import _source_units, named_section_bounds, topic_section_bounds, section_bounds, MAX_BRIEF_LENGTH
from chatbot.query_subject import compact, SERVICE_NAMES, service_names
from chatbot.question_intent import has_opening_hours, has_location_unit
from chatbot.source_scope import focus_units, focus_terms, detail_section_bounds, normalize_plain_source

FIELD = {
    'medical_details': r'(?:약품명|약명|복용량|용량|복용법)\s*[:：]|(?:복용|투여).{0,50}\d+\s*(?:mg|㎎|ml|㎖|정|회)',
    'conditions': r'제외|불가|안되는|안 되는|불필요|금지|제한|금식|자동가입|보장내용|용도\s*[:：]|지원대상|선정기준|소득인정액|지급금액|신청기간|예약|허\s*가\s*대\s*상|신\s*고\s*대\s*상|등록.*지원|단[,， ]|다만',
    'specifications': r'규격|크기|(?<![가-힣])(?:가로|세로)(?![가-힣])|\d+\s*(?:cm|㎝|매)',
    'eligibility': r'(?:^|—\s*)(?:(?:지원|진료|이용|신청|참여|접종|검진)?\s*대\s*상(?:자)?|청구주체|신청제외대상|지원제외|선정제외기준|납세의무자|피보험자|신청자격|연령기준|소득기준|거주기준|근로이력|취업기준|영양기준|영양위험요인|재산기준|자격|조건|참여조건|선정기준)\s*[:：]',
    'documents': r'준비물|구비\s*서류|지참물|신청서|신분증|확인증|산모수첩',
    'method': r'방법\s*[:：]|절차\s*[:：]|흐름도\s*[:：]|제출처\s*[:：]|인터넷.*신고|온라인.*발급|접수처|신청처|기부방법|신고처|배출요령|신청.*가능합니다|신청서.*제출|안내문.*우편.*발송|성명.*(?:기재|표기)|대문자|일반쓰레기는.*봉투|거래금액.*(?:보증금|월차임)|납부.*(?:카드|위택스)|(?:카드|위택스).*납부',
    'cost': r'\d[\d,.]*\s*(?:원|만원|%|퍼센트)|무료|무상|면제|본인\s*부담\s*없|(?:수\s*수\s*료|사용료|요금|금액|가격|처리비용)[^:：\n]{0,40}[:：].*\d',
    'schedule': r'(?:기간|시간|일자|시기|주기|공시|공표|납기|신청권수|신청수량|한도).{0,100}(?:\d|매년|연중|매주|매월)|\d\s*(?:월|일|개월|회|권|주|년)',
    'services': r'(?:운영|사업|서비스|진료|검사|검진|지원|상담)?내용\s*[:：]|민원증명\s*[:：]|처리업무\s*[:：]|급여\s*[:：]|서비스.*제공|서비스입니다|상담.*(?:제공|운영)|검진.*(?:무료|가능)|교육대상\s*[:：]|무료.*교육.*제공|(?:상담|접수|발급|신청).*(?:이용|가능|하실수)',
    'definition': r'^정의\s*[:：]|이란|말합니다|위함|목적으로|목적\s*[:：]|제도.*(?:입니다|함)|제공받고|일자리를\s*제공|사업(?:입니다|을\s*제공)|이다[.。]?$',
    'precautions': r'해야|마세요|하십시오|피하|피할|자제|삼가|대피|행동요령|금지|말 것|할 것',
    'necessity': r'공동.{0,8}이용|제출.*않|제출.*생략|불필요|제출.*필요|가입절차\s*[:：]|자동가입',
}


def field_matches(goal: str | None, unit: str, query: str = '', context: str = '') -> bool:
    if not source_unit_complete(unit):
        return False
    request = compact(query)
    scoped = context + ' ' + unit
    if (goal == 'method' and re.search(r'인터넷|온라인',request)
            and re.search(r'보건증|건강진단결과서|결과서',request)):
        return bool(re.search(r'온라인|인터넷',unit) and re.search(r'발급|출력|신청',unit))
    if goal == 'conditions' and re.search(r'대리|대신',request) and re.search(r'신청|발급|접수',request):
        if '여권' in request:
            from chatbot.passport_documents import applicant_age
            if applicant_age(query) == 'adult':
                return bool(re.search(r'본인.{0,8}직접.*방문신청',unit))
        return bool(re.search(r'대리|위임|법정대리|친권자|본인.{0,8}직접',unit))
    if goal == 'conditions' and re.search(r'신분증|증명서',request) and re.search(r'원본|사본|휴대폰사진|사진이면|사진으로',request):
        return bool(re.search(r'(?:신분증|증명서).{0,35}(?:사본|원본)|(?:사본|원본).{0,35}(?:신분증|증명서)',unit)
                    and re.search(r'가능|불가|필수|인정|허용|제출|지참',unit))
    if goal == 'conditions' and re.search(r'현금|계좌|통장',request) and re.search(r'지급|들어|받|나오',request):
        return bool(re.search(r'지급|바우처|국민행복카드|포인트|현금|계좌|통장',unit))
    if goal == 'conditions' and re.search(r'외국인',request):
        return bool(re.search(r'외국인|국적|내국인',unit))
    if goal == 'conditions' and re.search(r'전부사주|모두사주',request):
        return bool(re.search(r'선정제외|제외기준|제외대상',unit))
    if goal == 'eligibility' and re.search(r'\d+(?:세|살)|나이|연령',request) and re.search(r'심사기준.*\d+\s*세\s*(?:이상|미만|이하).*확인',unit):
        return True
    if goal == 'conditions' and re.search(r'제외|불가|금지', request):
        # "제외도서 확인" is an instruction to look up rules, not those rules.
        return bool(re.search(r'^(?:선정|신청|지원|이용)?\s*제외\s*(?:대상|기준|품목)\s*[:：]', unit)
            or re.search(r'제외(?:됩니다|합니다|대상|품목)|불가|금지|안되는|안 되는', unit))
    if goal == 'conditions' and re.search(r'되어도|되면|그대로받',request):
        ages = re.findall(r'\d{1,2}세',request)
        if ages and not any(age in compact(scoped) for age in ages):
            return False
    if goal == 'method' and re.search(
            r'^(?:처리|신청|접수|이용|예약|배출)방법\s+(?:[^\n]{0,180})(?:전화|문자|접수|신청|방문|제출|인터넷|온라인|콜센터)|'
            r'방\s*법\s*[:：]|배출.*(?:수거|봉투|요일|품목)|(?:요일|품목).*배출|수거.*(?:콜센터|예약|접수)|'
            r'(?:상담|민원).*국민신문고|인터넷.*(?:신청|열람|발급)|'
            r'(?:회원가입|로그인|본인인증|신분확인).*(?:필요|필수|먼저|후)',unit):
        return True
    if goal == 'schedule' and query:
        from chatbot.answer_goal import quantity_unit
        count_unit = quantity_unit(query)
        if count_unit:
            return bool(re.search(r'\d+\s*' + count_unit, unit))
        if re.search(r'한참뒤|출산.*(?:지나|지난|뒤)',request):
            return bool(re.search(r'신청기간|접수기간|신청시기',scoped))
        if re.search(r'배출|쓰레기',query) and re.search(r'아무때|낮|시간',query):
            return has_opening_hours(unit) and bool(re.search(r'배출|내어|내놓',unit))
        if re.search(r'당일.*(?:나와|발급|받)|다음날|며칠',request) and not re.search(r'며칠.*전',request):
            return bool(re.search(r'처리기간|소요|교부\s*[:：]|처리기한|\d+\s*일\s*(?:이내|정도)',unit))
        if re.search(r'며칠.*전|몇.*전',request):
            return bool(re.search(r'예약기간|신청기간|\d+\s*(?:일|주).*전',unit))
        if re.search(r'주기|몇년마다|몇번|자주',request):
            return bool(re.search(r'주기|횟수|\d+\s*(?:년|회|개월)|매(?:년|월|주)',unit))
    if goal == 'method' and re.search(r'계산|거래금액|환산',request):
        return bool(re.search(r'거래금액.*(?:보증금|월차임)|환산',unit))
    if goal == 'cost' and re.search(r'깎|감경|할인|감면',request):
        return bool(re.search(r'감경|할인|감면|자진납부',scoped)) and bool(re.search(FIELD['cost'],unit))
    if goal == 'cost' and re.search(r'기부.*까지만|기부한도|연간한도|상한',request):
        return bool(re.search(r'연간|개인별.*최대',unit))
    if goal == 'hours':
        if re.search(r'주말|공휴일|토요일|일요일',query) and not re.search(r'주말|공휴일|토요일|일요일',unit):
            return False
        return has_opening_hours(unit)
    if goal == 'location':
        return has_location_unit(unit) or bool(re.search(r'(?:신고처|접수처|기관명|소재지|시설명|주\s*소|위\s*치)\s*[:：]', unit))
    if goal == 'eligibility' and re.match(r'(?:지원대상|선정기준|이용대상|신청자격)\s*—',unit):
        return True
    if goal == 'conditions' and re.search(r'주소지|거주|사는사람',request) and re.search(r'기부',request):
        return bool(re.search(r'주소지|거주',unit) and re.search(r'제외|불가|제한|가능',unit))
    if goal == 'conditions' and re.search(FIELD['eligibility'],unit):
        return True
    return bool(goal and re.search(FIELD.get(goal, r'(?!)'), unit))


def scoped_units(query: str, body: str, keywords: set[str] | None = None) -> list[str]:
    units = _source_units(body.splitlines())
    bounds = detail_section_bounds(query, units)
    if bounds is None:
        bounds = topic_section_bounds(units,query,keywords) if keywords else named_section_bounds(units,query)
    units = units[bounds[0]:bounds[1]] if bounds else units
    detail = detail_section_bounds(query, units)
    if detail:
        units = units[detail[0]:detail[1]]
    return focus_units(query, units)


def requested_supported_items(query: str, units: list[str]) -> list[str]:
    """Name requested items only from an explicit support-test list."""
    if not any(re.search(r'지원\s*(?:시험\s*종류|대상\s*시험)',u) for u in units):
        return []
    output=[]
    for unit in units:
        if not source_unit_complete(unit) or not re.search(r'[:：].*[,，].*[,，]',unit):
            continue
        label,values=re.split(r'[:：]',unit,maxsplit=1)
        items=[]
        for value in re.split(r'[,，○]',values):
            name=value.strip()
            if not name or len(name)>30:
                continue
            pattern=r'(?<![가-힣A-Za-z0-9])'+re.escape(name)+r'(?=\s|[,，?.!]|이나|이랑|과|와|은|는|을|를|응시|$)'
            if re.search(pattern,query,re.I):
                items.append(name)
        if items:
            output.append('지원 시험 — '+label.strip()+': '+'·'.join(dict.fromkeys(items)))
    return output


def explicit_table_answer(query: str, units: list[str], title: str) -> str | None:
    """Read categorical lists and comparison cells with both axes intact."""
    request = compact(query)
    details = focus_terms(query)
    # Compare criteria printed in row identities, not an unrelated formula or
    # an arbitrary household-size amount. Values remain literal source text.
    if re.search(r'소득.*(?:같|차이)|(?:같|차이).*소득',request):
        subjects = {name for name in SERVICE_NAMES if name in request}
        labels = list(dict.fromkeys(u.split(' — ',1)[0] for u in units if ' — ' in u
            and re.search(r'중위.*\d+\s*%',u.split(' — ',1)[0])
            and any(name in compact(u.split(' — ',1)[0]) for name in subjects)))
        if len(labels) >= 2 and all(any(name in compact(label) for label in labels) for name in subjects):
            return '**' + title + '**\n' + '\n'.join('- ' + label for label in labels)
    rows = [u for u in units if ' — ' in u and ':' in u]
    # Category membership and its rule may occupy separate source sentences.
    # Require an explicit item INSIDE the category's balanced parentheses;
    # an adjacent category or an unlisted item cannot inherit this rule.
    if (answer_goal(query) == 'conditions' and re.search(r'봉투|배출|버리|넣',query)
            and not re.search(r'깨|파손|훼손|고장|누액|부푼|터진|분해|오염',query)):
        for unit in units:
            for sentence in re.split(r'(?<=[.!?])\s+',unit):
                rule = re.match(r'([가-힣]{2,16})(?:은|는)\s+.*(?:담지\s*않|혼합.*금지)',sentence)
                if not rule or not source_unit_complete(sentence):
                    continue
                category = rule.group(1)
                for row in rows:
                    start = re.search(re.escape(category)+r'\s*\(',row)
                    if not start:
                        continue
                    depth, end = 1, start.end()
                    while end < len(row) and depth:
                        depth += (row[end] == '(') - (row[end] == ')')
                        end += 1
                    if depth:
                        continue
                    members = row[start.end():end-1]
                    item_details = {d for d in details if d not in compact(sentence)}
                    item_details |= service_names(query) - {'쓰레기'}
                    proof = row + '\n- ' + sentence
                    if (item_details and all(d in compact(members) for d in item_details)
                            and all(d in compact(proof) for d in details)
                            and len(proof) <= MAX_BRIEF_LENGTH - 3):
                        return '- ' + proof
    # Boolean cells are meaningful only under an explicit eligibility caption.
    if re.search(r'면제|가능|대상',query) and re.search(r'면제|대상',title+' '.join(units[:2])):
        marks = [u for u in rows if re.search(r':\s*(?:○|◯|X|×)\s*$',u)
                 and any(t in compact(u.split(' — ',1)[1].split(':',1)[0]) for t in details)]
        if len(marks) == 1:
            unit = marks[0]
            label,mark = unit.rsplit(':',1)
            meaning = '면제 대상으로 안내됩니다.' if '면제' in title else '대상으로 표시되어 있습니다.'
            if mark.strip() in ('X','×'):
                meaning = '이 표에서는 대상이 아닌 것으로 표시되어 있습니다.'
            return label + ': **' + mark.strip() + '** — ' + meaning
    if answer_goal(query) == 'cost' and re.search(r'무료|무상',query):
        for row in rows:
            owner, field = row.split(' — ',1)
            if not re.match(r'품\s*명\s*:',field):
                continue
            items = [x.strip() for x in field.split(':',1)[1].split(',')]
            matches = [x for x in items if len(x) >= 2 and compact(x) in request]
            rules = [u.split(' — ',1)[1] for u in reversed(units[:units.index(row)]) if u.startswith(owner+' — ')
                     and re.match(r'분\s*류\s*:',u.split(' — ',1)[1])][:1]
            if not matches or not rules:
                continue
            proof = '·'.join(matches) + ' — ' + owner + '\n- ' + '\n- '.join(rules)
            qualifications = [u for u in units if QUALIFICATION.match(u) and
                              (compact(owner) in compact(u) or any(compact(x) in compact(u) for x in matches)) and len(u)<170
                              and not ('품목 中' in u and not any(compact(x) in compact(u) for x in matches))]
            proof += ''.join('\n- '+u for u in qualifications[:2])
            return proof if len(proof) <= 400 else None
    if answer_goal(query) == 'conditions' and details:
        focused = [u for u in rows if source_unit_complete(u) and
                   any(t in compact(u.split(' — ',1)[0]) for t in details)]
        content = [u for u in focused if re.search(r'조건|기준|보장내용|대상|용도',u.split(' — ',1)[1])]
        if content and len(content) <= 3:
            answer = '해당 조건을 충족하는지 확인해야 합니다. 공식 자료의 안내는 다음과 같습니다.\n'
            answer += '\n'.join('- '+u for u in content)
            return answer if len(answer) <= MAX_BRIEF_LENGTH else None
    return None


def structured_brief(query: str, document: dict, body: str, keywords: set[str]) -> dict | None:
    body = normalize_plain_source(body, str((document.get('metadata') or {}).get('title') or '공식 안내'))
    if not re.search(r'^#{2,6} ', body, re.M):
        return None
    goal = answer_goal(query)
    if goal == 'reference':
        return None
    units = scoped_units(query, body, keywords)
    if (goal == 'conditions' and '예약' in query and '학생' in query
            and not re.search(r'청소년|성인|\d+\s*(?:세|살)',query)
            and any(re.search(r'청소년.*예약',u) for u in units)):
        return {'answer':'공식 안내에서는 청소년의 예약을 구분하고 있습니다. **청소년인가요, 성인인가요?**',
                'is_clarification':True,'documents':[], 'answer_method':'structured_source',
                'reply_terms':['청소년','성인'],'suggested_questions':[]}
    if re.search(r'교육|훈련|강좌', query) and goal in (None,'method','location','schedule','services'):
        from chatbot.concise_answers import SCOPE_FIELD, course_scope_result
        audience = next((u for u in units if SCOPE_FIELD.match(u)), None)
        course = course_scope_result(query, audience)
        if course:
            return {**course, 'documents': [] if course['is_clarification'] else [document],
                    'answer_details': '', 'answer_method': 'structured_source',
                    'degraded': not course['is_clarification']}
    if goal is None:
        return None
    from chatbot.evidence import topic_support
    from chatbot.source_hierarchy import heading_path
    whole_units = _source_units(body.splitlines())
    ancestry = heading_path(whole_units,whole_units.index(units[0])) if units and units[0] in whole_units else ''
    if not topic_support({'content':'\n'.join(units)+' '+ancestry,'metadata':document.get('metadata') or {}},keywords)[0]:
        return None
    if goal == 'location':
        areas = re.findall(r'(?:괴정|당리|하단|신평|장림|다대|구평|감천)[1-4]?동', query)
        rows = [u for u in units if ' — ' in u and any(area in compact(u) for area in areas)]
        if rows:
            units = rows
        elif areas and any(' — ' in u and field_matches('location',u) for u in units):
            return {'answer':'요청하신 지역의 시설 위치는 이 자료에서 확인되지 않았습니다. **동 이름이나 인근 주소를 다시 알려주시겠어요?**',
                    'documents':[document],'is_clarification':True,'answer_method':'structured_source',
                    'reply_terms':['괴정','당리','하단','신평','장림','다대','구평','감천'],'suggested_questions':[]}
    scope = topic_section_bounds(_source_units(body.splitlines()), query, keywords)
    title = str((document.get('metadata') or {}).get('title') or '공식 안내')
    anchors = keywords.intersection(SERVICE_NAMES)
    details = focus_terms(query)
    # Income alone does not establish eligibility for crisis aid.
    reasons = [w for w in ('실직','질병','부상','폐업','휴업','화재','이혼') if w in query]
    if '위기사유' in body and '소득기준' in body and reasons and goal in ('eligibility','services','method'):
        whole = _source_units(body.splitlines())
        cause = [u for u in whole if not u.startswith('#') and any(w in u for w in reasons)
                 and source_unit_complete(u) and len(u) < 240]
        criteria = [u for u in whole if re.match(r'(?:소득|재산|금융재산)기준\s*[:：]',u) and source_unit_complete(u)]
        if cause and criteria:
            facts = [cause[0]] + criteria
            answer = '위기사유와 소득·재산 조건을 함께 확인해야 합니다.\n'+'\n'.join('- '+u for u in facts)
            if len(answer) <= MAX_BRIEF_LENGTH:
                return {'answer':answer,'documents':[document],'is_clarification':False,'answer_method':'structured_source',
                        'answer_details':title+'의 공식 안내 원문입니다.\n\n'+'\n'.join('> '+u for u in body.splitlines())}
    table_answer = explicit_table_answer(query, units, title)
    if table_answer:
        return {'answer':table_answer,'documents':[document],'is_clarification':False,
                'answer_method':'structured_source','answer_details':title+'의 공식 안내 원문입니다.\n\n'+'\n'.join('> '+u for u in body.splitlines())}
    if (goal in ('services','eligibility') and '위기사유' in body and '소득기준' in body
            and len(re.findall(r'^#{2,6} .*제\d+조 \d+호',body,re.M)) >= 3
            and not re.search(r'실직|질병|부상|폐업|휴업|화재|이혼|퇴원|입원',query)):
        reasons = [word for word in ('실직','질병','폐업','화재') if word in body]
        return {'answer':'위기사유와 소득·재산 조건을 함께 확인해야 합니다. **생계가 어려워진 이유('+'·'.join(reasons)+' 등)가 무엇인가요?**',
                'documents':[],'is_clarification':True,'answer_method':'structured_source',
                'reply_terms':reasons,'suggested_questions':[]}
    if ('암환자' in keywords and goal in ('services','eligibility','method') and '선정기준 — 의료급여수급자' in body
            and '선정기준 — 건강보험가입자' in body and not re.search(r'의료급여|차상위|건강보험',query)):
        return {'answer':'가입 유형에 따라 의료비 지원 조건이 다릅니다. **의료급여·차상위 대상자이신가요, 건강보험 가입자이신가요?**',
                'documents':[],'is_clarification':True,'answer_method':'structured_source',
                'reply_terms':['의료급여','차상위','건강보험'],'suggested_questions':[]}
    addresses = [u for u in units if ' — ' in u and re.search(r'(?:위치|주소|소재지)\s*[:：]',u)]
    if goal == 'location' and len(addresses) > 5 and not re.search(r'(?:괴정|당리|하단|신평|장림|다대|구평|감천)\d?동', query):
        return {'answer': '공식 자료에 동별 시설 목록이 있습니다. **어느 동이나 주소 근처의 시설**을 찾으시나요?',
                'documents': [], 'is_clarification': True, 'answer_method': 'structured_source',
                'reply_terms': ['괴정','당리','하단','신평','장림','다대','구평','감천'], 'suggested_questions': []}
    head_names = [compact(u.lstrip('# ')) for u in units if u.startswith('#')]
    competing = any(any(name in h for name in SERVICE_NAMES if name not in anchors) for h in head_names)
    from chatbot.evidence import topic_support
    page_scope = bool(anchors) and not competing and topic_support(
        {'content':body,'metadata':document.get('metadata') or {}}, anchors)[0]
    # Overview questions can name verified items without reproducing long
    # descriptions/amount tables. This only uses explicit source field labels.
    if goal == 'services' and re.search(r'급여.*무엇|어떤.*급여', query):
        names = list(dict.fromkeys(re.findall(r'^([^:：\n]{2,12}급여)\s*(?:[:：]|—)', body, re.M)))
        if len(names) >= 3:
            return {'answer': '공식 자료에 안내된 급여는 **' + '·'.join(names) + '**입니다. 급여별 대상과 지원 조건은 각각 다릅니다.',
                    'answer_details': title + '의 공식 안내 원문입니다.\n\n' + '\n'.join('> ' + u for u in body.splitlines()),
                    'documents': [document], 'is_clarification': False, 'answer_method': 'structured_source'}
    if goal == 'services' and re.search(r'종류', query):
        kinds = [u for u in units if u.startswith('종류 — ')]
        examples = []
        for unit in kinds:
            label, value = unit.split(':', 1)
            items = re.split(r'\s*\d+[.,]\s*', value.strip())
            items = [i.strip() for i in items if i.strip()]
            if len(items) < 3:
                return None
            examples.append(label.removeprefix('종류 — ') + ': ' + '·'.join(items[:2]) + ' 등')
        if examples and len('\n'.join(examples)) < 300:
            return {'answer': '공식 자료의 분류와 대표 예시는 다음과 같습니다.\n' + '\n'.join('- ' + e for e in examples),
                    'answer_details': title + '의 공식 안내 원문입니다.\n\n' + '\n'.join('> ' + u for u in body.splitlines()),
                    'documents': [document], 'is_clarification': False, 'answer_method': 'structured_source'}
    # A named row in a multi-service table has its own explicit subject.
    row_matches = [u for u in units if ' — ' in u and anchors and
                   all(a in compact(u.split(' — ', 1)[0]) for a in anchors - {'보건소'})]
    if row_matches and any(field_matches(goal, u) for u in row_matches):
        units = row_matches
    if goal == 'schedule':
        ranges = [u for u in units if re.match(r'\d+차 — 유효기간의 범위:',u)]
        methods = [u for u in units if re.search(r'예약.*내원.*검진.*결과|검진.*예약.*결과',u)]
        if len(ranges) > 4 and len(methods) == 1:
            overview = '\n'.join('- ' + u.replace(' — 유효기간의 범위:', ':') for u in ranges)
            answer = '**' + title + '**\n' + overview + '\n- ' + methods[0]
            if len(answer) <= MAX_BRIEF_LENGTH:
                return {'answer':answer,'answer_details':title+'의 공식 안내 원문입니다.\n\n'+'\n'.join('> '+u for u in body.splitlines()),
                        'documents':[document],'is_clarification':False,'answer_method':'structured_source'}
    selected = []
    missing = []
    partial_list = False
    goals = requested_goals(query)
    blocked = (document.get('metadata') or {}).get('unverified_fields') or []
    goals = tuple(f for f in goals if f not in blocked)
    if not goals:
        return None
    if (goal == 'services' and re.search(r'받을\s*수|있나요|가능',query)
            and not re.search(r'어떤|무슨|무엇|종류',query)):
        # Service availability is usefully answered with the program's actual
        # eligibility, then its access method. A title is still never a fact.
        if any(field_matches('eligibility',u) and len(u) <= 180 for u in units):
            goals = ('eligibility',)
        elif re.search(r'수거|가져가.*서비스', query) and any(
                field_matches('method', u, query) and re.search(r'수거|방문', u) for u in units):
            goals = ('method',)
    for field in goals:
        candidates = []
        def requested_row(unit):
            if ' — ' not in unit:
                return False
            owner = unit.split(' — ',1)[0]
            return any(len(compact(n))>=2 and not compact(n).isdigit() and compact(n) in compact(query) for n in re.split(r'[,·/]',owner))
        row_focus = any(requested_row(u) for u in units)
        general_targets = field == 'eligibility' and not row_focus and any(field_matches(field,u) and ' — ' not in u for u in units)
        for index, unit in enumerate(units):
            relevant_exception = (field in ('cost','eligibility','conditions') and QUALIFICATION.match(unit) and details
                                  and any(t in compact(unit) for t in details))
            if QUALIFICATION.match(unit) and field == 'conditions':
                relevant_exception = field_matches(field,unit,query)
            if QUALIFICATION.match(unit) and field == 'cost' and re.search(r'깎|감경|할인|감면',query):
                relevant_exception = field_matches(field,unit,query)
            heading_context = next((u for u in reversed(units[:index+1]) if u.startswith('#')),'')
            if (not field_matches(field, unit, query, heading_context) and not relevant_exception) or (QUALIFICATION.match(unit) and not relevant_exception) or len(unit) > 330:
                continue
            if general_targets and ' — ' in unit:
                continue
            # Table captions and explanatory headers never satisfy a field.
            if re.search(r'항목.*(?:구성|안내|표입니다)|다음과\s*같습니다\s*[.:：]?$', unit):
                continue
            section_heading = next((u.lstrip('# ') for u in reversed(units[:index + 1]) if u.startswith('#')), title)
            parents = [u.lstrip('# ') for u in units[:index + 1] if u.startswith('#')]
            # Use the nearest program heading, not a field such as '대상'.
            program = next((h for h in reversed(parents) if not re.fullmatch(r'(?:지원|사업|진료|운영|신청)?\s*(?:대상|내용|방법|자격|조건|기간|시간)|구비\s*서류', h)), title)
            vicinity = compact(program + ' ' + unit)
            matches = sum(k in vicinity for k in (anchors or keywords))
            # Once a program is scoped, field labels need not repeat its name.
            if anchors and not scope and not row_matches and not page_scope and not all(
                    k in compact(title) or k in vicinity for k in anchors):
                continue
            # A resident-wide inquiry cannot silently become a children-only
            # outreach program merely because both pages mention consultation.
            narrow = bool(re.search(r'소아|초등|지역아동센터|채용담당|사업자등록증|구인안내|노인·장애인|참여업체|업체\s*모집', unit + ' ' + program))
            if narrow and not re.search(r'소아|아동|아이|어린|초등|구인|사업자', query):
                continue
            resolved_field = field in ('eligibility','method') or (field == 'cost' and '지원' in query)
            score = (0 if resolved_field and (scope or page_scope) else matches * 5) + int(bool(re.search(r'^[^:：]{1,35}[:：]', unit))) * 3
            # Topic retrieval and requested detail are separate. A matching
            # service alone cannot choose the wrong certificate/table row.
            score += 10 * sum(t in compact(unit) for t in details)
            if requested_row(unit):
                score += 20
            score += 5 * sum(t in compact(section_heading) for t in details)
            if relevant_exception:
                score += 20
            if field == 'method' and re.search(r'인터넷|온라인', query):
                score += 12 if re.search(r'인터넷|온라인|위택스|공공보건포털', unit) else -10
            if field == 'cost' and re.search(r'지원', query):
                score += 15 if re.search(r'지원내용|지원금액|지원범위|지원한도|지원비율', section_heading + unit) else -10
            if field == 'cost' and re.search(r'깎|감경|할인|감면',query):
                if not re.search(r'깎|감경|할인|감면',section_heading+' '+unit):
                    continue
            if field == 'cost' and re.search(r'까지만|한도|연간|상한',query):
                score += 20 if re.search(r'연간|한도|최대',unit) else -10
            if field == 'cost' and re.fullmatch(r'계|합계',unit.split(':',1)[0].split('/')[-1].strip()):
                score += 15
            if field == 'definition':
                score += 20 if unit.startswith('정의:') else 0
            if field == 'schedule' and re.search(r'주말|공휴일|토요일|일요일',query):
                if not re.search(r'주말|공휴일|토요일|일요일',unit):
                    continue
            if field == 'services':
                score += 8 if re.search(r'^(?:운영|진료|지원|사업)내용\s*[:：]|급여\s*[:：]', unit) else 0
                score += 8 if re.search(r'민원증명\s*[:：]',unit) else 0
                if re.search(r'상담', query):
                    score += 10 if re.search(r'상담', unit) else -5
                if re.search(r'목적', unit):
                    score -= 10
            if field == 'eligibility':
                score += 12
            if field == 'hours' and not re.search(r'저녁|밤|야간|일과시간외',query):
                if re.search(r'야간|일과시간 외',section_heading + ' ' + unit):
                    continue
            if field == 'schedule' and '여권' in query and '유효' not in query and '유효' in compact(unit):
                continue
            if field == 'schedule' and '신청' in query:
                if re.search(r'며칠.*전|몇.*전',query) and not re.search(r'예약기간|일.*전|주.*전',unit):
                    continue
                score += 15 if re.search(r'신청|접수',section_heading + ' ' + unit) else -10
                if re.search(r'이용금지|조치사항',section_heading + ' ' + unit):
                    continue
            if field == 'schedule' and has_opening_hours(unit):
                score += 10
            if field == 'schedule' and not re.search(r'연납|선납',query):
                if re.search(r'연납|선납',section_heading + ' ' + unit):
                    continue
                if re.search(r'납기|정기',section_heading + ' ' + unit):
                    score += 12
            if field == 'schedule' and '공시' in query and not re.search(r'의견|이의',query):
                if re.search(r'의견|이의신청',section_heading + ' ' + unit):
                    continue
            candidates.append((score, index, unit))
        if not candidates:
            missing.append(field)
            continue
        candidates.sort(key=lambda item: (-item[0], item[1]))
        field_details = {t for t in details if t not in compact(title)}
        global_fee = field == 'cost' and ' — ' not in candidates[0][2] and bool(re.search(r'수수료.*(?:무료|무상)',candidates[0][2]))
        audience_column = any(' — ' in u and len(compact(u.split(' — ',1)[1].split(':',1)[0])) >= 3
                              and compact(u.split(' — ',1)[1].split(':',1)[0]) in compact(query) for u in units)
        supported_items = requested_supported_items(query, units)
        shared_support = field in ('cost','method') and bool(supported_items)
        if (not global_fee and not shared_support and not (audience_column and field in ('method','documents')) and field_details and any(t in compact(' '.join(units)) for t in field_details)
                and not any(t in compact(candidates[0][2]) or t in compact(
                    next((u for u in reversed(units[:candidates[0][1]+1]) if u.startswith('#')),''))
                            for t in field_details)):
            return None
        best_score = candidates[0][0]
        take = 6 if field == 'services' else 4 if field in ('eligibility', 'documents') else 3 if field in ('precautions','method') else 1 if field == 'definition' else 2
        for score, index, unit in candidates[:take]:
            if score < best_score - 4:
                continue
            if unit not in selected:
                selected.append(unit)
            if re.search(r'아래\s*(?:요건|조건).*모두', unit):
                # The introductory age row is not the whole eligibility.
                # Keep every requirement before the next field heading.
                end = next((i for i in range(index + 1,len(units)) if units[i].startswith('#')),len(units))
                requirements = [u.removeprefix('- ').strip() for u in units[index + 1:end]]
                if not requirements or not all(source_unit_complete(u) for u in requirements):
                    return None
                selected.extend(u for u in requirements if u not in selected)
            # Keep adjacent explicit exclusions/qualifications, even if they
            # make this result too long (then the normal planner must handle it).
            for next_unit in units[index + 1:index + 4]:
                if not QUALIFICATION.match(next_unit):
                    break
                if next_unit not in selected:
                    selected.append(next_unit)
        if field == 'conditions' and re.search(r'제외', query):
            exclusions = [u for _score, _index, u in candidates if re.match(
                r'^(?:선정|신청|지원|이용)?\s*제외\s*(?:대상|기준|품목)\s*[:：]', u)]
            partial_list = any(u not in selected for u in exclusions)
    if not selected:
        # A matched audience column can establish criteria even when an image
        # contains the application procedure. Do not substitute children's rules.
        labels = {compact(u.split(' — ',1)[1].split(':',1)[0]) for u in units if ' — ' in u}
        if goal in ('method','services') and any(len(l)>=3 and l in compact(query) for l in labels):
            facts = [u for u in units if ' — ' in u and field_matches('eligibility',u)]
            if facts and len(' '.join(facts)) < 350:
                selected = facts[:2]
                missing = ['method']
        elif goal == 'method' and scope and re.search(r'등록|신청',query):
            facts = [u for u in units if field_matches('documents',u) or field_matches('eligibility',u)]
            if facts and len(' '.join(facts)) < 350:
                selected = facts
                missing = ['method']
        if not selected:
            return None
    if (goal == 'method' and selected and all(re.match(r'^제출처\s*[:：]',u) for u in selected)):
        # A submission counter alone is a thin procedure answer. In its own
        # civil-service section, retain the complete short document set and
        # explicit filing deadline instead of inventing missing steps.
        requirements = [u for u in units if re.match(r'^(?:신청서\s*및\s*구비서류|구비서류|준비서류)\s*[:：]',u)]
        deadlines = [u for u in units if re.search(r'\d+\s*일\s*이내.*(?:신청|신고)',u)
                     and not u.startswith('#')]
        additions = requirements + deadlines
        if (additions and all(source_unit_complete(u) for u in additions)
                and len('\n'.join(selected + additions)) < 360):
            selected.extend(u for u in additions if u not in selected)
    # Comparison answers must establish both named programs. A formula for
    # one benefit is not a comparison merely because both occur on the page.
    comparison_subjects = keywords.intersection(SERVICE_NAMES)
    if len(comparison_subjects) > 1 and re.search(r'같|차이|비교',query):
        facts = compact(' '.join(selected))
        if not all(name in facts for name in comparison_subjects):
            return None
    audience_labels = {compact(u.split(' — ',1)[1].split(':',1)[0]) for u in units if ' — ' in u}
    matched_audience = {l for l in audience_labels if len(l)>=3 and l in compact(query)}
    audience_criteria = [u for u in units if ' — ' in u and field_matches('eligibility',u)
                         and compact(u.split(' — ',1)[1].split(':',1)[0]) in matched_audience]
    if goal in ('method','services') and audience_criteria:
        # Mandatory comparison-column conditions take precedence over a long
        # generic document list. Merely having documents is not eligibility.
        selected = list(dict.fromkeys(audience_criteria + [u for u in selected if len(u)<120]))
    if goal == 'cost' and ('무상' in keywords or re.search(r'무료|무상',query)):
        products = sorted(anchors - {'보건소'})
        if products and all(any(p in compact(u) and '가능제품 — ' in u for u in units) for p in products):
            selected.append('공식 단일수거 가능제품: ' + '·'.join(products))
        for u in units:
            if (QUALIFICATION.match(u) and any(p in compact(u) for p in products)
                    and re.search(r'제외|않음|불가|유상|부담',u) and source_unit_complete(u)):
                selected.append(u)
    # The same prerequisite/exception expansion used by model and fallback
    # readers applies here too. A schedule/benefit cannot drop its own target.
    from chatbot.concise_answers import condition_indices
    if (goal == 'method' and re.search(r'인터넷|온라인',query)
            and re.search(r'보건증|건강진단결과서|결과서',query)):
        selected.extend(u for u in units if re.search(r'검사일로부터.{0,30}발급',u)
                        and source_unit_complete(u) and u not in selected)
    indices = [units.index(u) for u in selected if u in units]
    for i in condition_indices(units, indices):
        if units[i] not in selected:
            selected.append(units[i])
    regions = {section_bounds(units,units.index(u)) for u in selected if u in units}
    if len(regions) == 1:
        start,end = regions.pop()
        units = units[start:end]
        scope = (start,end)
    if goal == 'services' and goals == ('eligibility',):
        # A yes/no availability request needs the actual benefit as well as
        # its target. Add a short same-program service field, never a new target.
        extra = [u for u in units if u not in selected and field_matches('services',u)
                 and re.match(r'^(?:지원|운영|진료|사업|서비스)?내용\s*[:：]',u)]
        for u in extra[:1]:
            if len(' '.join(selected)) + len(u) < 400:
                selected.append(u)
    # Useful adjacent prerequisites and verified access channels are retained
    # for method/service availability, not replaced by another service's fees.
    if goal in ('method', 'services', 'cost') and len(goals) == 1:
        labels = r'^(?:지참물|준비물|신청방법|이용방법|방법|온라인 발급|신청처|접수처|대\s*상|진료장소)\s*[:：]'
        for unit in units:
            if (unit not in selected and source_unit_complete(unit) and re.search(labels, unit)
                    and len(unit) < 170 and (scope or page_scope or len(head_names) <= 2)):
                if len(' '.join(selected)) + len(unit) < 350:
                    selected.append(unit)
    if goal == 'services':
        if '무료' in query:
            proofs=[u for u in units if '무료' in u and field_matches('cost',u)
                    and len(u)<170 and u not in selected]
            for unit in proofs[:1]:
                if len(' '.join(selected))+len(unit)<400:
                    selected.append(unit)
        for unit in requested_supported_items(query,units):
            if len(' '.join(selected))+len(unit)<400:
                selected.append(unit)
    heading = units[0].lstrip('# ') if scope and units[0].startswith('#') else title
    from chatbot.source_scope import is_field_heading
    if heading.endswith(('?','？')) or heading.startswith('※') or is_field_heading(heading) or compact(heading) in {'목적','지원사업소개'}:
        heading = title
    if goal == 'location':
        # Facility dimensions/capacity and UI link labels are not requested
        # location facts. Keep the name and address from the same owning row.
        display = []
        for unit in selected:
            if ' — ' in unit and ' · ' in unit:
                owner, cells = unit.split(' — ',1)
                cells = [c for c in cells.split(' · ') if re.match(r'(?:동명|시설명|기관명|장소|소재지|주\s*소|위\s*치)\s*[:：]',c)]
                display.append(owner+' — '+' · '.join(cells) if cells else unit)
            else:
                display.append(unit)
    else:
        display = selected
    answer = '**' + heading + '**\n' + '\n'.join('- ' + u for u in display)
    if partial_list:
        answer += '\n제외 기준 중 일부입니다. 전체 목록은 아래 공식 원문을 확인해 주세요.'
    unknown_details = {t for t in details if t not in compact(title) and
                       not any(t in compact(u) for u in units)}
    unresolved_detail = bool(unknown_details and goal in ('cost','conditions','specifications'))
    if goal in ('conditions','specifications') and unresolved_detail:
        # A shared topic word (e.g. 음식물) cannot prove an unseen detail
        # such as 라면 국물. Keep the uncertainty explicit across all readers.
        from chatbot.source_scope import unanswered_details
        unresolved_detail = bool(unanswered_details(query,' '.join(selected),title,keywords))
        if unresolved_detail:
            return None
    if unresolved_detail:
        answer += '\n문의하신 세부 항목·포함 범위는 이 자료에서 확인되지 않았습니다.'
    if missing:
        labels = {'location':'장소','hours':'운영시간','documents':'구비서류','method':'신청·이용 방법','cost':'비용','schedule':'기간·일정','eligibility':'대상·조건','services':'서비스 내용'}
        fields = '·'.join(labels.get(f,'요청 항목') for f in missing)
        answer += '\n'+fields+' 정보는 이 자료에서 명확히 확인되지 않았습니다.'
    if len(answer) > MAX_BRIEF_LENGTH:
        return None
    if goal == 'location' and re.search(r'상담|진료|검사', query):
        for u in units:
            if (re.match(r'^(?:이용|예약|신청)방법\s*[:：]',u) and source_unit_complete(u)
                    and len(answer) + len(u) + 3 <= MAX_BRIEF_LENGTH):
                answer += '\n- ' + u
                break
    if goal in ('eligibility','services') and len(selected) <= 2:
        from chatbot.answer_enrichment import enrich_answer
        answer = enrich_answer(query, answer, '\n'.join(units), keywords, heading)
    return {'answer': answer, 'answer_details': title + '의 공식 안내 원문입니다.\n\n' + '\n'.join('> ' + u for u in body.splitlines()), 'degraded':bool(missing) or unresolved_detail or partial_list,
            'documents': [document], 'is_clarification': False, 'answer_method': 'structured_source'}
