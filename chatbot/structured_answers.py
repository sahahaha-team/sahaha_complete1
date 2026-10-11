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
from chatbot.query_subject import compact, SERVICE_NAMES
from chatbot.question_intent import has_opening_hours, has_location_unit

FIELD = {
    'eligibility': r'(?:^|—\s*)(?:(?:지원|진료|이용|신청|참여|접종|검진)?\s*대\s*상(?:자)?|납세의무자|피보험자|신청자격|연령기준|소득기준|거주기준|영양기준|영양위험요인|재산기준|자격|조건|참여조건|선정기준)\s*[:：]',
    'documents': r'준비물|구비\s*서류|지참물|신청서|신분증|확인증|산모수첩',
    'method': r'방법\s*[:：]|절차\s*[:：]|인터넷.*신고|온라인.*발급|접수처|신청처|기부방법|신고처|배출요령|신청.*가능합니다|안내문.*우편.*발송|성명.*(?:기재|표기)|대문자|일반쓰레기는.*봉투',
    'cost': r'\d[\d,.]*\s*(?:원|만원|%|퍼센트)|무료|무상|본인\s*부담\s*없',
    'schedule': r'(?:기간|일자|시기|주기|공시|공표|접수시간).{0,100}(?:\d|매년|연중)|\d\s*(?:월|일|개월|회)',
    'services': r'(?:운영|사업|서비스|진료|검사|검진|지원|상담)?내용\s*[:：]|처리업무\s*[:：]|급여\s*[:：]|서비스.*제공|서비스입니다|상담.*(?:제공|운영)|검진.*(?:무료|가능)|교육대상\s*[:：]|무료.*교육.*제공|(?:상담|접수|발급|신청).*(?:이용|가능|하실수)',
    'definition': r'^정의\s*[:：]|이란|말합니다|위함|목적으로|목적\s*[:：]|제도.*(?:입니다|함)|제공받고|일자리를\s*제공|사업(?:입니다|을\s*제공)|이다[.。]?$',
    'precautions': r'해야|마세요|하십시오|피하|피할|자제|삼가|대피|행동요령|금지|말 것|할 것',
    'necessity': r'공동.{0,8}이용|제출.*않|제출.*생략|불필요|제출.*필요|가입절차\s*[:：]|자동가입',
}


def field_matches(goal: str | None, unit: str) -> bool:
    if not source_unit_complete(unit):
        return False
    if goal == 'hours':
        return has_opening_hours(unit)
    if goal == 'location':
        return has_location_unit(unit) or bool(re.search(r'(?:신고처|접수처|기관명|소재지|시설명|주\s*소|위\s*치)\s*[:：]', unit))
    if goal == 'eligibility' and re.match(r'(?:지원대상|선정기준|이용대상|신청자격)\s*—',unit):
        return True
    return bool(goal and re.search(FIELD.get(goal, r'(?!)'), unit))


def scoped_units(query: str, body: str, keywords: set[str] | None = None) -> list[str]:
    units = _source_units(body.splitlines())
    bounds = topic_section_bounds(units,query,keywords) if keywords else named_section_bounds(units,query)
    return units[bounds[0]:bounds[1]] if bounds else units


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


def structured_brief(query: str, document: dict, body: str, keywords: set[str]) -> dict | None:
    if not re.search(r'^#{2,6} ', body, re.M):
        return None
    goal = answer_goal(query)
    if goal in (None, 'reference'):
        return None
    units = scoped_units(query, body, keywords)
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
    if (goal in ('services','eligibility') and '위기사유' in body and '소득기준' in body
            and len(re.findall(r'^#{2,6} .*제\d+조 \d+호',body,re.M)) >= 3
            and not re.search(r'실직|질병|부상|폐업|휴업|화재|이혼|퇴원|입원',query)):
        reasons = [word for word in ('실직','질병','폐업','화재') if word in body]
        return {'answer':'위기사유와 소득·재산 조건을 함께 확인해야 합니다. **생계가 어려워진 이유('+'·'.join(reasons)+' 등)가 무엇인가요?**',
                'documents':[],'is_clarification':True,'answer_method':'structured_source',
                'reply_terms':reasons,'suggested_questions':[]}
    if (goal in ('services','eligibility') and '선정기준 — 의료급여수급자' in body
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
        elif any(field_matches('definition',u) for u in units):
            goals = ('definition',)
    for field in goals:
        candidates = []
        general_targets = field == 'eligibility' and any(field_matches(field,u) and ' — ' not in u for u in units)
        for index, unit in enumerate(units):
            if not field_matches(field, unit) or QUALIFICATION.match(unit) or len(unit) > 330:
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
            narrow = bool(re.search(r'초등|지역아동센터|채용담당|사업자등록증|구인안내|노인·장애인', unit + ' ' + program))
            if narrow and not re.search(r'아동|아이|어린|초등|구인|사업자', query):
                continue
            resolved_field = field in ('eligibility','method') or (field == 'cost' and '지원' in query)
            score = (0 if resolved_field and (scope or page_scope) else matches * 5) + int(bool(re.search(r'^[^:：]{1,35}[:：]', unit))) * 3
            if field == 'method' and re.search(r'인터넷|온라인', query):
                score += 12 if re.search(r'인터넷|온라인|위택스|공공보건포털', unit) else -10
            if field == 'cost' and re.search(r'지원', query):
                score += 15 if re.search(r'지원내용|지원금액|지원범위|지원한도|지원비율', section_heading + unit) else -10
            if field == 'services':
                score += 8 if re.search(r'^(?:운영|진료|지원|사업)내용\s*[:：]|급여\s*[:：]', unit) else 0
                if re.search(r'상담', query):
                    score += 10 if re.search(r'상담', unit) else -5
                if re.search(r'목적', unit):
                    score -= 10
            if field == 'eligibility':
                score += 12
            if field == 'schedule' and has_opening_hours(unit):
                score += 10
            if field == 'schedule' and '공시' in query and not re.search(r'의견|이의',query):
                if re.search(r'의견|이의신청',section_heading + ' ' + unit):
                    continue
            candidates.append((score, index, unit))
        if not candidates:
            return None  # Let the model inspect semantics; do not substitute a different field.
        candidates.sort(key=lambda item: (-item[0], item[1]))
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
    if not selected:
        return None
    if goal == 'cost' and ('무상' in keywords or re.search(r'무료|무상',query)):
        products = sorted(anchors - {'보건소'})
        if products and all(any(p in compact(u) and '가능제품 — ' in u for u in units) for p in products):
            selected.append('공식 단일수거 가능제품: ' + '·'.join(products))
        for u in units:
            if (QUALIFICATION.match(u) and any(p in compact(u) for p in products)
                    and re.search(r'제외|않음|불가|유상|부담',u) and source_unit_complete(u)):
                selected.append(u)
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
    if goal in ('method', 'services', 'cost'):
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
    if heading.endswith(('?','？')) or compact(heading) in {'목적','지원사업소개'}:
        heading = title
    answer = '**' + heading + '**\n' + '\n'.join('- ' + u for u in selected)
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
    return {'answer': answer, 'answer_details': title + '의 공식 안내 원문입니다.\n\n' + '\n'.join('> ' + u for u in body.splitlines()),
            'documents': [document], 'is_clarification': False, 'answer_method': 'structured_source'}
