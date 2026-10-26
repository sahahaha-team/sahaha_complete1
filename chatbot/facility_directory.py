"""Read location rows from one current official facility directory."""
import re
from chatbot.query_subject import compact
from chatbot.question_intent import asks_location
from chatbot.verified_facts import _fresh

AREA = re.compile(r'(?:괴정|당리|하단|신평|장림|다대|구평|감천)[1-4]?동')
DIRECTORIES = {
    '작은도서관': 'https://www.saha.go.kr/portal/contents.do?mId=0607030000',
    '마을건강센터': 'https://www.saha.go.kr/health/contents.do?mId=0404050000',
}


def directory_records(body, kind):
    records=[]
    if kind=='작은도서관':
        active=False
        current=None
        def finish():
            if current and current.get('category')=='작은도서관' and current.get('address'):
                records.append(current)
        for line in body.splitlines():
            if line.startswith('#'):
                if '참여도서관' in compact(line):
                    active=True
                    continue
                if active:
                    break
            if not active:
                continue
            match=re.match(r'([^—]+) — (도서관|전화번호|주소|비고):\s*(.+)',line)
            if not match:
                continue
            owner,field,value=match.groups()
            if field=='도서관':
                finish()
                current={'name':value,'category':owner.strip()}
            elif current and current['category']==owner.strip():
                key={'전화번호':'phone','주소':'address','비고':'note'}[field]
                if key in current and current[key]!=value:
                    current['invalid']=True
                current[key]=value
        finish()
    else:
        by_name={}
        for line in body.splitlines():
            match=re.match(r'([^—]+) — (위치|주소|전화번호):\s*(.+)',line)
            if not match:
                continue
            name,field,value=match.groups()
            if not AREA.fullmatch(compact(name)):
                continue
            record=by_name.setdefault(name,{'name':name+' 마을건강센터'})
            key='phone' if field=='전화번호' else 'address'
            if key in record and record[key]!=value:
                record['invalid']=True
            record[key]=value
        records=list(by_name.values())
    # Reject conflicting duplicates rather than publishing whichever row won.
    by_name = {}
    invalid = set()
    for record in records:
        name = compact(record['name'])
        if record.get('invalid') or (name in by_name and record != by_name[name]):
            invalid.add(name)
        by_name[name] = record
    return [r for name, r in by_name.items() if r.get('address') and name not in invalid]


def select_records(records, query):
    text=compact(query)
    areas=AREA.findall(text)
    candidates=records
    if areas:
        def matches(record,area):
            owned=AREA.findall(compact(record['name']))
            return any(a==area or (not re.search(r'\d',area) and re.sub(r'\d','',a)==area) for a in owned)
        candidates=[r for r in records if all(matches(r,a) for a in areas)]
    names=[]
    for r in candidates:
        stem=AREA.sub('',compact(r['name'])).replace('작은도서관','').replace('마을건강센터','').replace('어린이','')
        if len(stem)>=3 and stem in text:
            names.append(r)
    return names or (candidates if areas else [])


def facility_directory(query,client):
    text=compact(query)
    kinds=[k for k in DIRECTORIES if k in text]
    if len(kinds)!=1 or re.search(r'담당|팩스|fax|전화로',text,re.I):
        return None
    kind=kinds[0]
    if kind=='마을건강센터' and re.search(r'백신|접종|검사|진료|치매|금연|소아|임신',text):
        return None  # A facility address does not prove a specific clinical service.
    wants_phone=bool(re.search(r'전화번호|연락처|전화만',text))
    if not asks_location(query) and not wants_phone and not re.search(r'가까운|근처|인근|주변',text):
        return None
    if re.search(r'시간|수수료|비용|준비물|서류|신청|예약|대상|자격|조건|이용료|언제',text):
        return None  # Do not drop a second field the directory cannot establish.
    from database_db.raw_pages import read_raw_pages
    try:
        rows=read_raw_pages(client,'url,title,content,raw_html,last_checked_at',url=DIRECTORIES[kind],limit=1)
    except Exception:
        return None
    if not rows or not (checked:=_fresh(rows[0].get('last_checked_at'))):
        return None
    from chatbot.official_content import official_html_text
    body=official_html_text(rows[0].get('raw_html') or '') or rows[0].get('content') or ''
    records=directory_records(body,kind)
    if not records:
        return None
    chosen=select_records(records,query)
    if wants_phone and kind=='작은도서관' and not chosen and not AREA.search(text):
        return None  # Programme inquiry is distinct from a branch phone.
    source={'title':rows[0].get('title') or kind+' 공식 목록','url':DIRECTORIES[kind],
            'checked_at':checked,'source_type':'verified_page'}
    if not chosen:
        if AREA.search(text):
            return {'answer':'이 공식 목록에서는 말씀하신 동의 시설을 확인하지 못했습니다. 다른 동의 시설을 같은 지역의 시설로 안내할 수는 없습니다.',
                    'sources':[source],'is_clarification':False,'degraded':True,'degraded_reason':'facility_not_listed','suggested_questions':[],
                    'evidence':{'status':'insufficient','label':'시설 확인 필요','official_source_count':1,'answer_method':'facility_directory'}}
        return {'answer':f'**어느 동의 {kind}**를 찾으시나요? 동 이름이나 시설명을 알려주세요.',
                'is_clarification':True,'reply_terms':['괴정','당리','하단','신평','장림','다대','구평','감천']+[r['name'] for r in records],
                'suggested_questions':[],'answer_method':'facility_directory'}
    if wants_phone and any(not r.get('phone') for r in chosen):
        return None
    lines=[]
    for r in chosen:
        line='- **'+r['name']+'**: '+r['address']
        if r.get('note'):
            line+=' / '+r['note']
        if wants_phone:
            line+=' / 전화 '+r['phone']
        lines.append(line)
    answer='공식 시설 목록의 안내입니다.\n'+'\n'.join(lines)
    if kind=='작은도서관' and re.search(r'교육|강좌|프로그램',query):
        answer+='\n위 주소는 시설 주소입니다. 개별 강좌의 실제 수업 장소는 해당 모집공고에서 확인해야 합니다.'
    if len(answer)>480:
        return {'answer':'해당 지역에 시설이 여러 곳 있습니다. **어느 시설**을 찾으시나요?',
                'is_clarification':True,'reply_terms':[r['name'] for r in chosen], 'suggested_questions':[], 'answer_method':'facility_directory'}
    return {'answer':answer,'sources':[source],'is_clarification':False,'degraded':False,'degraded_reason':None,'suggested_questions':[],
            'evidence':{'status':'official','label':'공식 시설 목록 확인됨','official_source_count':1,'answer_method':'facility_directory'}}
