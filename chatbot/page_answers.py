"""Select complete official fields for a question, retaining their context."""
from __future__ import annotations
import math
import re
from chatbot.query_subject import compact, substantive_keywords
from chatbot.question_intent import requested_field_score, asks_navigation, asks_tax_liability, asks_location as asks_location_local
from chatbot.source_text import clean_source_text


def select_sections(query, body, sections, topics, tokens=()):
    topics = substantive_keywords(topics)
    fields, seen = [], {}
    for section in sections:
        text = clean_source_text(section.get('text') or '')
        heading = clean_source_text(section.get('heading') or '')
        if not text or re.fullmatch(r'(?:PDF뷰어 다운로드|PDF 다운로드|다운로드|바로가기|\s)+', text, re.I):
            continue
        if text in seen:
            previous = fields[seen[text]]
            if heading.count(' / ') > previous['heading'].count(' / '):
                previous['heading'] = heading
            continue
        seen[text] = len(fields)
        fields.append({'heading': heading, 'text': text})
    if not fields:
        return clean_source_text(body), ''
    if len(fields) > 1:
        fields = [f for f in fields if not ('|' in f['heading'] and len(f['text']) > 500)] or fields
    # A parent can own a substantive table as well as child instructions.
    # Its length alone does not make it a redundant whole-page container.
    if re.search(r'주민.*행동|특보.*어떻게', query) and not re.search(r'직장|학교|산업|건설|농가|축사', query):
        household = [f for f in fields if re.search(r'일반\s*가정', f['heading'])]
        if household:
            fields = household
    # An explicitly named subprogram owns its fields. A different program's
    # amount or application form must not win merely by matching the intent.
    branches = {part for f in fields for part in f['heading'].split(' / ')
                if compact(part) in topics}
    if branches:
        focused = [f for f in fields if any(part in f['heading'].split(' / ') for part in branches)]
        if focused:
            fields = focused
    if asks_tax_liability(query):
        liability = [(f['heading'], line.strip()) for f in fields for line in f['text'].splitlines()
                     if re.match(r'납세의무자\s*[:：]', line.strip())]
        liability = list(dict.fromkeys(liability))
        if len(liability) > 1:
            return '\n\n'.join(heading + '\n' + line for heading, line in liability), '납세의무자'
    if re.search(r'급여.*(?:무엇|종류)|(?:무엇|종류).*급여', query):
        benefits = {}
        for field in fields:
            for label in field['heading'].split(' / '):
                match = re.match(r'([^:：]{2,16}급여)\s*[:：]', label)
                if match:
                    benefits.setdefault(match[1], label)
        if benefits:
            return '\n'.join('- ' + label for label in benefits.values()), '급여 종류'
    # DOM extraction can miss a definition in a bare div before the first h3.
    first = fields[0]['heading'].split(' / ')[-1]
    clean_body = clean_source_text(body)
    if first in clean_body:
        introduction = clean_body.split(first, 1)[0].strip()
        if len(introduction) >= 55 and len(introduction) <= 600 and not re.search(r'제\d+조|Step\s*\d|지원대상', introduction):
            fields.insert(0, {'heading': introduction.splitlines()[0], 'text': introduction})
    words = {compact(t) for t in tokens if len(compact(t)) >= 2}
    words -= {'알리', '있다', '하다', '받다', '어떻', '어떻게', '무엇', '나요', '사하구', '사하', '청'}
    def score(section):
        heading, value = compact(section['heading']), compact(section['text'])
        direct = sum(len(word) for word in topics if word in heading)
        matches = sum((1 + math.log(1 + len(fields) / (1 + sum(word in compact(f['text']) for f in fields))))
                      for word in words if word in value)
        leaf = section['heading'].split(' / ')[-1]
        focus = requested_field_score(query, leaf)
        if asks_location_local(query):
            focus = requested_field_score(query, section['heading'])
        body_focus = requested_field_score(query, section['text'][:500])
        penalty = 0
        if not re.search(r'비용|수수료|요금|진료비|얼마|금액', query) and re.search(r'진료비|수수료|요금|자동계산', compact(leaf)):
            penalty += 10
        if re.search(r'어떤.*(?:서비스|진료)|무엇|서비스.*이용', query) and re.search(r'위치|운영시간|진료절차', leaf):
            penalty += 10
        if re.search(r'인터넷|온라인', query) and not re.search(r'인터넷|온라인|위택스|정부24|복지로', section['text']):
            penalty += 12
        if '구직' in query and re.search(r'구직정보|구직등록', leaf): matches += 20
        if re.search(r'서비스|받을\s*수|지원.*있나요|사업인가요', query) and not asks_navigation(query) and not asks_location_local(query):
            if re.search(r'^(?:지원내용|사업목적|운영내용|내용|사업개요)$', compact(leaf)): matches += 12
            if re.search(r'지원대상|소득기준|사업대상', compact(leaf)): matches += 6
            if re.search(r'제\d+조\d+호', compact(leaf)): penalty += 15
        if re.search(r'주민.*행동|특보.*어떻게', query) and re.search(r'일반가정', compact(leaf)): matches += 12
        if re.search(r'어떤사업|무엇인가|뭐야|무엇이고', compact(query)) and re.search(r'개요|목적|소개|이란|정의|사업$', compact(leaf)):
            matches += 20
        if re.search(r'서비스(?:가)?있', compact(query)) and re.search(r'서비스\s*입니다|정보\s*제공\s*서비스', section['text']):
            matches += 30
        if asks_location_local(query) and re.search(r'위치|장소|이용안내', compact(leaf)): matches += 12
        if re.search(r'온라인|인터넷', query) and re.search(r'인터넷|온라인', section['text']): matches += 18
        if not asks_location_local(query) and re.search(r'받을\s*수|사업인가요', query) and re.search(r'소득기준|지원대상|사업대상', compact(leaf)): matches += 12
        # A subprogram nested under the requested service is not its general
        # instruction (e.g. a detailed-test subsidy under ordinary screening).
        parts = section['heading'].split(' / ')
        for position, part in enumerate(parts[:-1]):
            if any(word == compact(part) for word in topics):
                penalty += 10 * sum(bool(re.search(r'지원|사업|검사|서비스', extra))
                                    and compact(extra) not in compact(query) for extra in parts[position+1:-1])
        if '물기' in query and '물기' in value: matches += 8
        if re.search(r'자주|몇.*회|주기', query) and re.search(r'연\s*\d+\s*회|월\s*\d+\s*회|매년|주기', section['text']): matches += 10
        if re.search(r'어떻게|행동|대처|요령', query):
            matches += min(24, 5 * len(re.findall(r'할\s*것|마세요|대피|피하|피한다|하지\s*말|안\s*된다|않도록|금지', section['text'])))
        if re.search(r'이미|다시.*제출|재제출', query) and '공동이용' in heading: matches += 12
        if re.search(r'자동|따로.*가입|별도.*가입', query) and re.search(r'자동가입|별도.*가입|가입절차', value): matches += 10
        if re.search(r'영문|성명', query) and '영문' in heading: matches += 10
        if re.search(r'정해진기간.*아니|기간.*아니어도|연중', query) and '연중' in heading: matches += 10
        return min(4, direct) + matches + focus * 7 + body_focus * 3 - penalty
    ranked = sorted(enumerate(fields), key=lambda pair: score(pair[1]), reverse=True)
    index, selected = ranked[0]
    chosen = {index}
    listing = bool(re.search(r'무엇|종류|서비스.*에는|어떤.*(?:진료|사업)|어떻게.*이용', query))
    compound = bool(re.search(r'누가.*(?:서류|가져)|무엇.*언제|언제.*어떻게|비용.*기간|시간.*위치|받을\s*수|사업인가요|기간.*아니', query))
    best = score(selected)
    for other, section in ranked[1:]:
        if len(chosen) >= (5 if listing else 3 if compound else 2):
            break
        related_heading = any(w in compact(section['heading']) for w in topics)
        if (listing and related_heading and score(section) >= best * .4
                or compound and (score(section) >= best * .5 or re.search(r'소득기준|지원대상|사업목적', section['heading']))
                or abs(other-index) == 1 and re.search(r'기준|예외|주의|예약|신청|제외', section['heading'])
                   and score(section) >= best * .6):
            chosen.add(other)
    # Put the best field first so a long supporting table cannot hide it.
    chosen_order = [index] + [i for i in sorted(chosen) if i != index]
    passages = [fields[i]['heading'] + '\n' + fields[i]['text'] for i in chosen_order]
    if re.search(r'대상.*어떻게.*확인|자격.*확인', query):
        lookups = [line.strip() for f in fields for line in f['text'].splitlines()
                   if re.search(r'(?:대상자|자격).*조회\s*[:：]', line)]
        if lookups:
            passages.insert(1, '\n'.join(dict.fromkeys(lookups)))
    if re.search(r'조건|자격|받을\s*수', query) and not re.search(r'얼마|금액|비용', query):
        reasons = [f for f in fields if re.search(r'위기사유', f['heading'])]
        if len(reasons) >= 3:
            # Show all first-line crisis categories rather than implying that
            # an income threshold alone is sufficient. Details stay folded.
            parent = reasons[0]['heading'].rsplit(' / ', 1)[0]
            overview = parent + '\n' + '\n'.join('- ' + re.split(r'(?<=경우)|(?<=\.)\s', f['text'], maxsplit=1)[0].strip() for f in reasons)
            passages.insert(1, overview)
    return '\n\n'.join(passages), selected['heading']


def page_brief(query, body, title):
    current_limits = re.search(r'부양의무자.{0,20}소득\s*연\s*([\d.]+)억원[·\s]*일반재산\s*([\d.]+)억원', body)
    other_limits = re.search(r'고소득\(연([\d.]+)억\).*?고재산\(([\d.]+)억\)', body)
    if current_limits and other_limits and current_limits.groups() != other_limits.groups():
        general = [line.split('→', 1)[0].strip() for line in body.splitlines()
                   if line.startswith(('지원대상 :', '선정기준 :'))]
        if general:
            return '\n\n'.join(general) + '\n\n부양의무자의 세부 금액 기준이 공식 원문 안에서 서로 다르게 기재되어 있습니다. 해당 기준은 담당 부서에 확인이 필요합니다.'
    if '[이미지 문자 인식 자료:' in body:
        closure = re.search(r'운영\s*중단\s*및\s*철거가\s*확정\s*되었습니다\.', body)
        if closure:
            return '**' + title.split('|')[0].strip() + '**\n\n' + closure.group(0) + '\n\n공식 이미지 공지입니다. 이용 전 아래 원문을 확인하세요.'
    if asks_navigation(query):
        return f'**{title.split("|")[0].strip()}** 안내에서 확인할 수 있습니다. 아래 공식 출처에서 전체 내용을 확인하세요.'
    if '종류' in query:
        rows = [line.split(' | ') for line in body.splitlines() if ' | ' in line]
        header = next((row for row in rows if row[0] == '구분'), None)
        kinds = next((row for row in rows if row[0] == '종류'), None)
        if header and kinds and len(header) == len(kinds):
            examples = []
            for label, value in zip(header[1:], kinds[1:]):
                names = [part.strip() for part in re.split(r'(?<!\d)\d+[.,]\s*', value) if part.strip()]
                examples.append('- ' + label + ': ' + ', '.join(names[:3]) + (' 등' if len(names) > 3 else ''))
            return '\n'.join(examples) + '\n\n종류별 예시입니다. 전체 목록과 신고 기준은 아래 원문에서 확인하세요.'
    if len(body) > 1100 and re.search(r'언제.*어떻게', query):
        # Show the age/date schedule and procedure before a long table of
        # examination items. The complete original remains in answer_details.
        blocks = body.split('\n\n')
        blocks.sort(key=lambda block: (bool(re.search(r'절차|예약|검진일 기준|유효기간', block)),
                                       not bool(re.search(r'검진항목 \|', block))), reverse=True)
        body = '\n\n'.join(blocks)
    if len(body) <= 1800:
        return body
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    prefix = []
    for line in lines:
        if len('\n'.join(prefix + [line])) > 1100:
            break
        prefix.append(line)
    if not prefix:
        return None
    return '\n'.join(prefix) + '\n\n전체 표·세부 조건은 아래 원문과 공식 출처에서 확인하세요.'
