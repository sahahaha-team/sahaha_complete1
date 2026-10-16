"""Question focus and source ownership, independent of particular FAQ answers."""
from __future__ import annotations

import re
from functools import lru_cache

from chatbot.query_subject import compact, SERVICE_NAMES, WEAK_WORDS, AREA_PATTERN, service_names

FIELD_LABEL = re.compile(r'^(?:신청대상|신청권수|신청방법|선정제외기준|신청기간|처리절차|청구주체|신청대상|준비물|구비서류|지원내용|상담내용|이용시간|진료시간|제외대상|지원제외|납부기간|납기|예약방법|처리기간|대상|내용|방법|수수료|위치|문의)$')
FOCUS_STOP = WEAK_WORDS | set('구청 보건소 나이 주민등록증 주민등록 신청인 이유 이용 기준 무료 무상 신규 등록 서류 준비물 검사 치료 병원 주사 차이 똑같 사람 장소 채택 결과 필요 친구 낮 밤 직장 상태 계좌 중 하나 모든 전부 꼭 아무 이용권 받을 통장 보건지원 세금 도움 청구'.split())
AREAS = re.compile(r'(?:괴정|당리|하단|신평|장림|다대|구평|감천)[1-4]?동')
FOCUS_STOP.update('가정 자녀 부분 상세 운영 주차장 공영 이름 방식 각종 성명 매 기간 최대 과정 하루'.split())
FOCUS_STOP.update({'인터넷','홈페이지','웹사이트','온라인','당일','다음','예전','주민센터','그대로','영문','등록','기관'})
FOCUS_STOP.update({'점심','저녁','낮','밤','증명서','클리닉'})
FOCUS_STOP.update({'이사','전입','갱신','신용카드','계좌이체'})
FOCUS_STOP.update({'요청','시험','응시','선정','개방','정도','임신'})
FOCUS_STOP.update({'주소','위치','장소','연락처','전화','번호','운영시간','서류','절차',
                   '제외','한도','권수','횟수'})
FOCUS_STOP.update({'부탁','상한'})
FOCUS_STOP.update({'기한','퍼센트','비율','연락','요청','진행','고충','예약','수강료'})


@lru_cache(maxsize=256)
def focus_terms(query: str) -> frozenset[str]:
    """Keep detail words for selecting rows; never require them in every chunk."""
    from chatbot.query_subject import normalize_query, strip_general_question_tail
    text = AREA_PATTERN.sub(' ', strip_general_question_tail(normalize_query(query)))
    text = text.replace('대신','대리')
    from chatbot.query_subject import WORDING_ALIASES
    for alias, target in WORDING_ALIASES.items():
        text = text.replace(alias, target)
    matches = [(m.start(),-len(name),name) for name in SERVICE_NAMES
               if (m := re.search(r'\s*'.join(map(re.escape,name)),text,re.I))]
    primary = min(matches)[2] if matches else ''
    if primary:
        text = re.sub(r'\s*'.join(map(re.escape,primary)), ' ', text, flags=re.I)
    text = AREAS.sub(' ', text)
    try:
        from chatbot.bm25_index import _init_kiwi
        words = {compact(t.form) for t in _init_kiwi().tokenize(text)
                 if t.tag.startswith('NN') or t.tag == 'SL'}
    except Exception:
        words = set(re.findall(r'[가-힣a-zA-Z]{2,}', text))
    return frozenset(w for w in words if len(w) >= 2 and w not in FOCUS_STOP
                     and (not primary or w not in compact(primary)))


def unanswered_details(query: str, selected: str, title: str, keywords: set[str]) -> frozenset[str]:
    """A service match alone cannot establish a requested specific item.

    Semantic ranking may bridge the service's wording. It does not authorize
    silently discarding a detail absent from the chosen source facts.
    """
    details = {t for t in focus_terms(query) if t not in compact(title)
               and not any(t in k or k in t for k in keywords)}
    value = compact(selected)
    if re.search(r'바우처|국민행복카드|포인트|현금|계좌|통장',value):
        details -= {'현금','계좌','통장'}  # Payment alternatives answer the same field.
    if re.search(r'본인.{0,8}직접|대리|위임',value):
        details.discard('대리')
    if '청소년' in query and '청소년' in selected:
        details.discard('학생')  # A confirmed age group, not an inferred one.
    if re.search(r'법원|재판',query) and re.search(r'소송.*진행|불복.*진행',selected):
        details -= {'법원','재판','진행'}
    if '여권' in compact(query) and re.search(r'\d+(?:세|살)',compact(query)):
        details -= {'대학','학생','대학생','고등학생','초등학생'}  # Explicit legal age is retained separately.
    return frozenset(t for t in details if t not in compact(selected))


def normalize_plain_source(body: str, title: str) -> str:
    """Label headings present in older text-only rows, without supplying facts."""
    if re.search(r'^#{2,6} ', body, re.M):
        output=[]; field=None
        for line in body.splitlines():
            heading=re.match(r'^#{2,6}\s+(.+)',line)
            if heading:
                name=heading.group(1).strip().rstrip(':：')
                field=name if is_field_heading(name) else None
                output.append(line)
            elif field and line.strip() and not re.search(r'[:：]| — ',re.sub(r'\d{1,2}:\d{2}', '', line)) and not line.lstrip().startswith(('※','❖','다만','단,','단 ')):
                output.append(field+': '+line)
            else:output.append(line)
        return '\n'.join(output)
    if ' — ' in body:
        return '## ' + title + '\n' + body
    from chatbot.concise_answers import _section_headings
    if _section_headings(body.splitlines()):
        return body  # Older named program headings already retain their scope.
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not any(FIELD_LABEL.fullmatch(re.sub(r'\s+','',line).rstrip(':：')) for line in lines):
        return body
    output = ['## ' + title]
    label = None
    for line in lines:
        name = re.sub(r'\s+', '', line).rstrip(':：')
        if FIELD_LABEL.fullmatch(name):
            label = name
            output.append('### ' + line.rstrip(':：'))
        elif re.search(r'이란\??$|제도란\??$', line):
            label = '정의'
            output.append('### ' + line)
        elif re.match(r'^[^:：]{1,30}[:：]\s*\S', line):
            # A clock embedded in a field's value is not another label.
            if label and re.match(r'^\d',line):
                output.append(label + ': ' + line)
                continue
            label = None
            output.append(line)
        elif line != title:
            output.append(label + ': ' + line if label and not line.startswith(('※','❖','다만')) else line)
    return '\n'.join(output)


def is_field_heading(name: str) -> bool:
    value=compact(name).rstrip(':：?？')
    return bool(FIELD_LABEL.fullmatch(value) or re.search(
        r'(?:방법|절차|기간|시간|서류|준비물|자격|조건|요건|기준|위치|주소|연락처|수수료|이용료|지원내용|사업내용|배출요령|제외품목|제외항목)$',value))


def focus_units(query: str, units: list[str]) -> list[str]:
    """A matching dong selects the entire owning row, across all field goals."""
    areas = AREAS.findall(query)
    from chatbot.vaccination import is_vaccination_query
    if is_vaccination_query(query) and '검사' not in query:
        units = [u for u in units if ' — ' not in u or '검사' not in u.split(' — ',1)[0]]
    groups: dict[str, list[str]] = {}
    for unit in units:
        if ' — ' in unit:
            groups.setdefault(unit.split(' — ', 1)[0], []).append(unit)
    if areas and groups:
        matching = {key for key, rows in groups.items()
                    if any(area in compact(' '.join(rows)) for area in areas)}
        if matching:
            units = [u for u in units if ' — ' not in u or u.split(' — ',1)[0] in matching]
            groups = {key:rows for key,rows in groups.items() if key in matching}
    request = compact(query)
    from chatbot.answer_goal import requested_goals
    if 'documents' in requested_goals(query):
        # A source's explicitly labelled applicant rows are alternatives.
        # Common documents remain; a directly visiting heir needs no proxy row.
        roles=('상속인','대리인','본인')
        wanted={role for role in roles if role in request}
        if re.search(r'대리|위임',request):
            wanted={'대리인'}
        if wanted:
            units=[u for u in units if not (m:=re.match(r'(?:구비서류|준비서류)\s*[:：]\s*(상속인|대리인|본인)\s*신청',u))
                   or m[1] in wanted]
    # A test mentioned inside a bundled panel is not a standalone fee/guide.
    bundled = {key for key in groups if '[' in key and ',' in key
               and compact(key.split('[',1)[0]) not in request}
    if bundled:
        units = [u for u in units if ' — ' not in u or u.split(' — ',1)[0] not in bundled]
        groups = {k:v for k,v in groups.items() if k not in bundled}
    # Comparison tables can put their audience in a column, not a row.
    column_names = {compact(u.split(' — ',1)[1].split(':',1)[0]) for u in units
                    if ' — ' in u and ':' in u}
    columns = {name for name in column_names if len(name) >= 3 and name in request
               and re.search(r'가입자|수급자|경감대상자|가구|가정|장애인|유공자',name)}
    if columns:
        longest = max(map(len, columns))
        columns = {c for c in columns if len(c) == longest}
        units = [u for u in units if ' — ' not in u or ':' not in u or
                 compact(u.split(' — ',1)[1].split(':',1)[0]) in columns]
        groups = {k:[u for u in values if u in units] for k,values in groups.items()}
    named = []
    for key in groups:
        name = compact(re.sub(r'\([^)]*\)|\[[^\]]*\]', '', key))
        name = re.sub(r'검사(?:비용)?$','',name)
        names = [compact(n) for n in re.split(r'[,·/]', key)]
        if '등본' in request:
            names += [n.replace('등초본','등본') for n in names]
        if any(len(n) >= 3 and n in request for n in names):
            named.append((max(len(n) for n in names if len(n) >= 3 and n in request),key))
        if len(name) >= 2 and not name.isdigit() and name in request:
            named.append((len(name),key))
    if named:
        keys = {key for _,key in named}
        def identity_hits(key):
            parts = re.split(r'[,·/]',key)
            score = 0
            for part in parts:
                name = compact(re.sub(r'\([^)]*\)|\[[^\]]*\]','',part))
                short = re.sub(r'검사(?:비용)?$','',name)
                if len(name)>=2 and name in request:
                    score += len(name)
                elif len(short)>=2 and short in request:
                    score += len(short)
            return score
        best = max(identity_hits(key) for key in keys)
        matching = {key for key in keys if identity_hits(key) == best}
        return [u for u in units if ' — ' not in u or u.split(' — ',1)[0] in matching]
    return units


def detail_section_bounds(query: str, units: list[str]) -> tuple[int, int] | None:
    """Prefer an explicitly requested subsection, such as 철분제 or 영아종일제."""
    terms = focus_terms(query)
    # A detail word such as 안전 may occur in a sibling program. Once a
    # requested service owns a heading, details must stay inside that scope.
    subjects = service_names(query) - {'보건소','구청','쓰레기','디지털','컴퓨터'}
    service_scopes = []
    for index, unit in enumerate(units):
        if not subjects or not unit.startswith('#') or not all(s in compact(unit) for s in subjects):
            continue
        level = len(unit) - len(unit.lstrip('#'))
        end = next((i for i in range(index+1,len(units)) if units[i].startswith('#')
                    and len(units[i])-len(units[i].lstrip('#')) <= level),len(units))
        service_scopes.append((index,end))
    candidates = []
    for index, unit in enumerate(units):
        if not unit.startswith('#'):
            continue
        if service_scopes and not any(start <= index < end for start,end in service_scopes):
            continue
        name = compact(unit.lstrip('# '))
        if name.endswith(('유의사항','주의사항','란?','란？')) or re.search(r'란[?？]$', unit):
            continue
        from chatbot.answer_goal import requested_goals
        if name.endswith(('구비서류','준비서류')) and 'documents' not in requested_goals(query):
            continue
        if FIELD_LABEL.fullmatch(name) or name in {'위치및운영시간','대상및기준','사업기간','신청안내','선정기준','지원대상및기준','문의','상담문의'}:
            continue
        hits = sum(term in name for term in terms)
        if not hits:
            continue
        level = len(unit) - len(unit.lstrip('#'))
        end = next((i for i in range(index + 1,len(units)) if units[i].startswith('#')
                    and len(units[i])-len(units[i].lstrip('#')) <= level),len(units))
        candidates.append((hits, index, end))
    if not candidates:
        # A benefit may be named in the facts, while its heading says e.g.
        # "우대차량 등록". Use the unique strongest factual occurrence and
        # retain its owning section, including audience and exceptions.
        # Never let one generic detail word pick a sibling field/benefit.
        if len(terms) < 2:
            return None
        from chatbot.concise_answers import section_bounds
        factual = []
        for index, unit in enumerate(units):
            if unit.startswith('#'):
                continue
            if service_scopes and not any(start <= index < end for start, end in service_scopes):
                continue
            hits = sum(term in compact(unit) for term in terms)
            if hits >= 2:
                factual.append((hits, section_bounds(units, index)))
        if not factual:
            return None
        best = max(hits for hits, _bounds in factual)
        winners = {bounds for hits, bounds in factual if hits == best}
        return next(iter(winners)) if len(winners) == 1 else None
    best = max(c[0] for c in candidates)
    winners = [(start,end) for hits,start,end in candidates if hits == best]
    return winners[0] if len(winners) == 1 else None
