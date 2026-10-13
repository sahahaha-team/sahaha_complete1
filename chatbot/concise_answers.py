"""Short answers from verified source text, with intact details kept separately."""
from __future__ import annotations

import re

from chatbot.query_subject import compact, substantive_keywords, SERVICE_NAMES
from chatbot.answer_goal import answer_goal, GOAL_WORDS
from chatbot.question_intent import (
    asks_opening_hours, has_opening_hours, asks_location, has_location_unit, location_source_units,
)
from chatbot.vaccination import vaccination_place_brief, is_vaccination_query
from chatbot.answer_completion import (
    OMISSION, QUALIFICATION, complete_source_units, source_unit_complete, can_continue,
)

MAX_BRIEF_LENGTH = 480
SCOPE_FIELD = re.compile(r"^(?:교육)?(?:대\s*상|신청자격|지원대상|이용대상|조건)\s*[:：]")


def _section_headings(units: list[str]) -> list[int]:
    headings = []
    structured = any(re.match(r'^#{2,6} ', u) for u in units)
    for i, unit in enumerate(units):
        if re.match(r'^#{2,6} ', unit):
            value = unit.lstrip('# ')
            if value.endswith(('?', '？')) and re.search(r'공시일|기간|시간|방법|절차|대상|조건|자격|비용|서류', value):
                continue  # A requested field question is not another program.
            if re.fullmatch(r'(?:질환|소득|재산|연령|거주|영양|근로|취업)\s*기준|근로이력',value):
                continue
            if not re.fullmatch(r'(?:지원|신청|교육|진료|사업|운영|이용)?\s*(?:대상|내용|방법|기간|시간|자격|조건)|구비\s*서류|준비물|\d{4}년\s*선정기준액', value) and compact(value) not in {
                    '위치및운영시간','사업목적','운영원리','핵심운영원리','검진시기및항목','신청안내','문의','상담문의','연락처','처리업무','제외대상','사업개요','사업기간','신청서접수처','신청자격','참여자격배제대상','대상자선발방법','선발시고려요소가중치적용','임금및근로조건','대상자선정기준','선정기준','배경','신청','목적','지원대상및기준','신청절차','지원대상및내용','지원절차','서류안내','검진항목','검진절차','검사항목','지원항목','이용시간및이용료'} and not re.search(r'신청기준|적용기준$|^\d+[.]\s*(?:지원내용|주의사항|신청서류)|(?:이용시|이용 시)\s*(?:유의|주의)사항$|^\d{4}년.*판정기준$', value):
                headings.append(i)
            continue
        if structured:
            continue
        # Some headings include their own hours after an arrow. Those hours
        # belong to the new service, not to the previous clinic's table.
        heading = re.split(r'\s*[▹▷]', unit, maxsplit=1)[0].strip()
        if 6 <= len(heading) <= 60 and (
                (not source_unit_complete(unit) and re.search(r'(?:교육|프로그램|사업|서비스)$', heading))
                or (not re.search(r'[:：\d]', heading) and re.search(
                    r'(?:클리닉\s*(?:운영)?|상담전화\s*안내)(?:\s*\([^)]*\))?$', heading))):
            headings.append(i)
    return headings


def section_bounds(units: list[str], index: int) -> tuple[int, int]:
    """Separate named activities from the next activity on a multi-service page."""
    headings = _section_headings(units)
    start = max((i for i in headings if i <= index), default=0)
    level = len(units[start]) - len(units[start].lstrip('#')) if headings else 0
    current_name = compact(units[start]) if units else ''
    end = min((i for i in headings if i > index and
               (not level or len(units[i]) - len(units[i].lstrip('#')) <= level
                or ('상담전화' in compact(units[i]) and '국가' in compact(units[i]) and '국가' not in current_name))), default=len(units))
    return start, end


def named_section_bounds(units: list[str], query: str) -> tuple[int, int] | None:
    """Prefer the longest explicitly requested program heading on this page."""
    matches = []
    headings = _section_headings(units)
    for pos, start in enumerate(headings):
        name = re.split(r'[▹▷]', units[start].lstrip('# '), maxsplit=1)[0].strip()
        if name.endswith(('?', '？')):
            continue  # A field question is not a separate requested program.
        # Parenthesized tax/service names can contain the requested subtype.
        if '(' in name and compact(name) not in compact(query):
            name = name.split('(', 1)[0].strip()
        name = compact(re.sub(r'\s*(?:운영|안내|정보)$', '', name))
        matches_name = (len(name) >= 4 or name in SERVICE_NAMES) and (name in compact(query) or
            ('주민세' in name and '주민세' in compact(query)) or
            ('성인예방접종' in name and '성인예방접종' in compact(query)))
        if matches_name:
            _, end = section_bounds(units, start)
            matches.append((len(name), start, end))
    if not matches:
        return None
    best = max(length for length, _, _ in matches)
    winners = [(start, end) for length, start, end in matches if length == best]
    return winners[0] if len(winners) == 1 else None


def topic_section_bounds(units: list[str], query: str, keywords: set[str]) -> tuple[int,int] | None:
    """Use the smallest unique program containing the requested subjects."""
    explicit = named_section_bounds(units, query)
    from chatbot.answer_goal import requested_goals
    if explicit and len(requested_goals(query)) > 1:
        return explicit
    subjects = keywords.intersection(SERVICE_NAMES) or (substantive_keywords(keywords) - {'보건소','구청','무상'})
    if not subjects:
        return explicit
    if (not explicit and units and re.match(r'^## ',units[0])
            and re.search(r'(?:진료실|보건실|민원실)$',compact(units[0]))
            and all(s in compact(units[0]) for s in subjects)):
        return section_bounds(units,0)
    regions, body_regions = [], []
    for start in _section_headings(units):
        bounds = section_bounds(units,start)
        if explicit and not explicit[0] <= start < explicit[1]:
            continue
        heading = compact(units[start])
        # Facts/documents can mention another program incidentally. Only a
        # program name in the heading can narrow a structured page's scope.
        if all(s in heading for s in subjects):
            regions.append(bounds)
        elif all(s in compact(' '.join(units[bounds[0]:bounds[1]])) for s in subjects):
            body_regions.append(bounds)
    if not regions:
        regions = body_regions
    exact = [r for r in regions if compact(re.sub(r'\s*(?:운영|안내|정보)$','',units[r[0]].lstrip('# ')))
             == ''.join(sorted(subjects))]
    if exact:
        regions = exact
    if regions and requested_goals(query):
        # A provider list can repeat the program name while omitting its age
        # or period. Prefer the region which actually contains the requested
        # fields before choosing the smallest subsection.
        from chatbot.structured_answers import field_matches
        fields = requested_goals(query)
        def coverage(bounds):
            region = units[bounds[0]:bounds[1]]
            count = sum(any(field_matches(field,u,query) for u in region) for field in fields)
            requested_rows = sum(' — ' in u and any(len(compact(p))>=2 and not compact(p).isdigit()
                and compact(p) in compact(query) for p in re.split(r'[,·/]',u.split(' — ',1)[0]))
                and any(field_matches(field,u,query) for field in fields) for u in region)
            return (bool(requested_rows),count)
        best = max(coverage(r) for r in regions)
        regions = [r for r in regions if coverage(r) == best]
    smallest = [r for r in regions if not any(r != s and r[0] <= s[0] and s[1] <= r[1] for s in regions)]
    return smallest[0] if len(smallest)==1 else explicit


def condition_indices(units: list[str], indices: list[int]) -> list[int]:
    """Keep field scope and adjacent exceptions beside a selected fact."""
    chosen = set(indices)
    for index in indices:
        section_start, section_end = section_bounds(units, index)
        if re.search(r'아래\s*(?:요건|조건).*모두',units[index]):
            for pos in range(index + 1,min(section_end,index + 7)):
                if pos in _section_headings(units):
                    break
                requirement = units[pos].removeprefix('- ').strip()
                if source_unit_complete(requirement) and re.match(r'(?:거주|근로|소득|재산|취업|연령|사업자).*[:：]',requirement):
                    chosen.add(pos)
        for pos in range(index + 1, min(section_end, index + 6)):
            if QUALIFICATION.match(units[pos]):
                chosen.add(pos)
            else:
                break
        for pos in sorted(range(max(section_start, index - 4), min(section_end, index + 5)),
                          key=lambda p: abs(p - index)):
            if SCOPE_FIELD.match(units[pos]):
                chosen.add(pos)
                break
    return sorted(chosen)


def course_scope_result(query: str, audience: str | None) -> dict | None:
    """Clarify a documented course's audience once; do not repeat after a no."""
    if not audience or not any(word in query for word in ('교육', '훈련', '강좌')):
        return None
    value = re.split(r'[:：]', audience, maxsplit=1)[-1].strip()
    if re.fullmatch(r'(?:사하)?구민|(?:사하구)?주민|시민|누구나', compact(value)):
        # A general resident program has no missing age/role choice. Retain
        # its audience in the answer instead of asking a redundant question.
        return None
    if any(word in compact(query) and word in compact(value)
           for word in ('공동주택', '관리자', '책임자', '다중이용', '어린이', '학생', '사업주', '근로자')):
        return None
    if any(word in compact(query) for word in ('일반', '주민', '구민')):
        if not any(word in value for word in ('주민', '구민', '누구나', '시민')):
            return {"answer": f"확인된 교육은 {value} 대상입니다. 일반 주민이 신청할 수 있는 교육의 장소·일정은 이 자료에서 확인되지 않았습니다.",
                    "is_clarification": False, "suggested_questions": []}
        return None
    return {"answer": f"확인된 교육은 {value} 대상입니다.\n이 대상의 교육을 찾으시나요?",
            "answer_details": "", "is_clarification": True, "suggested_questions": [],
            "affirmative_context": value, "negative_context": "일반 주민",
            "reply_terms": ["네", "맞아", "아니", "일반", "주민", "관리", "책임자"]}


def source_lines(original_answer: str) -> list[str]:
    return [line[2:].strip() for line in original_answer.splitlines() if line.startswith("> ")]


def _passport(query: str, body: str) -> str | None:
    if re.search(r'수령|교부|증명',query):
        return None
    if any(word in query for word in ("기간", "며칠", "소요")) and '유효기간' not in query:
        line = next((line for line in body.splitlines() if re.match(r"여권교부\s*:", line)), None)
        return line if line and len(line) < MAX_BRIEF_LENGTH else None
    if not any(word in query for word in ("서류", "준비", "구비")):
        return None
    if any(word in query for word in ('미성년', '아이', '자녀', '18세미만')):
        lines = [line for line in body.splitlines() if line.startswith(('미성년자의 사진 및 구여권', '친권자(', '미성년자 본인', '미성년자의 2촌'))]
        answer = '\n'.join('- ' + line for line in lines)
        return answer if len(lines) == 2 and len(answer) <= MAX_BRIEF_LENGTH else None
    if any(word in query for word in ("긴급", "관용")):
        return None
    photo = re.search(r"여권용 컬러 사진\s*(\d+매)\(([^)]+)\)", body)
    if not photo or "여권발급신청서 1부" not in body or "신분증" not in body:
        return None
    answer = f"준비물은 **여권발급신청서 1부·신분증·여권용 사진 {photo.group(1)}**입니다."
    answer += "\n\n사진 기준: " + photo.group(2) + "."
    if "유효기간 남은 여권은 지참" in body:
        answer += "\n유효기간이 남은 기존 여권도 지참하세요."
    return answer


def _parking(query: str, body: str) -> str | None:
    if "신고" not in query or any(word in query for word in ("이의", "과태료", "견인", "의견진술")):
        return None
    required = ("신고방법", "안전신문고", "동일한 위치와 방향", "1분 이상", "사진 2장 이상", "촬영시간", "당일 및 익일")
    if not all(word in body for word in required):
        return None
    return ("불법주정차는 **안전신문고 앱**에서 신고하세요.\n\n"
            "- 같은 차량을 같은 위치·방향에서 **1분 이상 간격으로 사진 2장 이상** 촬영하세요.\n"
            "- 위반 위치·차량번호·촬영시각이 보여야 합니다.\n"
            "- **촬영 당일 또는 다음 날**까지 신고하세요. 구역별 운영시간·요건은 원문에서 확인할 수 있어요.")


def _waste(query: str, body: str) -> str | None:
    if not any(word in query for word in ("배출", "버리", "방법", "접수")) or any(word in query for word in ("비용", "수수료", "얼마")):
        return None
    required = ("처리업체에 직접 전화", "문자 접수", "051-266-1170~1", "맑은사하환경", "1:1톡 접수", "무상수거")
    if not all(word in body for word in required):
        return None
    return ("대형폐기물은 **맑은사하환경(051-266-1170~1)**에 전화·문자로 접수하세요. "
            "카카오톡 ‘맑은사하환경’ 1:1 접수도 가능합니다.\n\n"
            "일부 가전제품은 무상수거 대상입니다. **어떤 물품을 버리시는지** 알려주시면 해당 안내를 확인할게요.")


def _source_units(lines: list[str]) -> list[str]:
    units = complete_source_units(lines)
    # A standalone method/eligibility heading followed by complete prose is
    # a source field. Never join arbitrary monetary or multi-column cells.
    headings = {"신청방법", "접수방법", "이용방법", "신고방법", "지원대상", "교육대상", "준비물", "진료절차", "대상", "진료내용", "지원내용", "신청자격"}
    list_headings = {"운영내용", "사업내용", "서비스내용", "진료내용", "지원내용"}
    output = []
    index = 0
    while index < len(units):
        if units[index].startswith('#'):
            output.append(units[index])
            index += 1
            continue
        if compact(units[index]) in list_headings:
            items = []
            end = index + 1
            while end < len(units) and len(items) < 5:
                item = units[end]
                if (any(word in compact(item) for word in ("운영시간", "신청방법", "신청대상", "지원대상", "수수료", "전화번호", "위치", "준비물"))
                        or QUALIFICATION.match(item) or can_continue(item) or item == OMISSION
                        or re.fullmatch(r"[\d, .]+(?:원|명|세)?", item) or len(item) < 8):
                    break
                items.append(item)
                end += 1
            if items and len(" · ".join(items)) <= 300:
                output.append(units[index] + " : " + " · ".join(items))
                index = end
                continue
        if (compact(units[index]) in headings and index + 1 < len(units)
                and (source_unit_complete(units[index + 1]) or
                     (len(units[index + 1]) >= 8 and not can_continue(units[index + 1])
                      and not re.fullmatch(r"[\d, .]+(?:원|명|세)?", units[index + 1])
                      and units[index + 1] != OMISSION))
                and not QUALIFICATION.match(units[index + 1])):
            output.append(units[index] + " : " + units[index + 1])
            index += 2
        else:
            output.append(units[index])
            index += 1
    return output


def _extract_brief(query: str, lines: list[str], keywords: set[str], title: str = "") -> str | None:
    location = answer_goal(query) == "location"
    units = location_source_units(lines) if location else _source_units(lines)
    from chatbot.source_scope import focus_units, detail_section_bounds
    detail = detail_section_bounds(query,units)
    if detail:
        units = units[detail[0]:detail[1]]
    units = focus_units(query,units)
    from chatbot.evidence import topic_support
    if not topic_support({'content':'\n'.join(units),'metadata':{'title':title}},keywords)[0]:
        return None
    requested_section = topic_section_bounds(units, query, keywords)
    topics = substantive_keywords(keywords)
    opening_hours = asks_opening_hours(query)
    goal = answer_goal(query)
    intent = list(GOAL_WORDS.get(goal, ()))
    heading = compact(title + " " + " ".join(lines[:3]))
    anchors = topics.intersection(SERVICE_NAMES)
    heading_scope = not title or (bool(anchors) and anchors.issubset({word for word in anchors if word in heading})) or (
        not anchors and sum(word in heading for word in topics) >= max(1, len(topics) * .75))
    if intent and any(word in query for word in ("배출", "재활용", "분리수거")):
        intent += ["배출", "분리"]
    # Only complete factual prose/label-value units. Standalone cells such as
    # '58면', '52,000원' cannot be reassigned to another row or condition.
    candidates = []
    for i, unit in enumerate(units):
        if requested_section and not requested_section[0] <= i < requested_section[1]:
            continue
        label_value = bool(re.search(r"[:：]\s*[가-힣 ]{6,}", unit))
        hours_unit = has_opening_hours(unit)
        place_unit = has_location_unit(unit)
        if (len(unit) < 22 and not label_value and not hours_unit and not place_unit) or len(unit) > 350 or unit.startswith(("Q.", "[…]")):
            continue
        if opening_hours and not hours_unit:
            continue
        if opening_hours and not re.search(r'야간|저녁|밤|일과시간외',query):
            nearby = ' '.join(units[max(0,i-2):i+1])
            if re.search(r'야간|일과시간 외|18:30\s*[~∼]',nearby):
                continue
        if location and not place_unit:
            continue
        if not source_unit_complete(unit):
            continue
        matched_field = False
        if goal in ('conditions','cost','schedule','eligibility','services','definition','precautions','necessity','method','specifications','documents'):
            from chatbot.structured_answers import field_matches
            if not field_matches(goal,unit,query):
                continue
            matched_field = True
        if QUALIFICATION.match(unit):
            continue
        # Omitted context and an unfinished preceding condition cannot be
        # silently detached from an otherwise complete statement.
        if i and (units[i - 1] == OMISSION or can_continue(units[i - 1])):
            continue
        if i + 1 < len(units) and units[i + 1] == OMISSION:
            continue
        value = compact(unit)
        topic_hits = sum(word in value for word in topics)
        goal_hits = sum(compact(word) in value for word in intent) + int(matched_field)
        if goal == "method" and re.search(r"(?:하세요|하십시오|마세요|해야 합니다)[.!]?$", unit):
            goal_hits += 1
        if goal == "schedule" and any(word in query for word in ("자주", "주기", "몇 번")):
            goal_hits = int(bool(re.search(r"(?:연|월|주|일)\s*\d+\s*회|매(?:년|월|주|일)", unit)))
        section_start, section_end = section_bounds(units, i)
        local = compact(" ".join(units[max(section_start, i - 12):min(section_end, i + 13)]))
        local_scope = bool(topics) and all(word in local for word in (anchors or topics))
        if not topic_hits and not heading_scope and not local_scope:
            continue
        if intent and not goal_hits and not (opening_hours and hours_unit) and not (location and place_unit):
            continue
        if topic_hits or goal_hits or (opening_hours and hours_unit) or (location and place_unit) or (not intent and heading_scope):
            field_bonus = 8 if goal == "services" and re.match(r"(?:운영|사업|서비스|진료|지원)내용\s*:", unit) else 0
            candidates.append((topic_hits * 4 + goal_hits + int(heading_scope) + field_bonus, i))
    if not candidates:
        return None
    for _, start in sorted(candidates, key=lambda item: (-item[0], item[1])):
        chosen = [units[index] for index in condition_indices(units, [start])]
        if goal == 'eligibility':
            # Subcriteria under one program apply together. An age row alone
            # must not imply eligibility when income/residency also constrain it.
            begin, end = section_bounds(units,start)
            for criterion in units[begin:end]:
                value = criterion.removeprefix('- ').strip()
                if (re.match(r'^(?:거주|소득|재산|연령|근로|취업|영양)(?:기준|이력|위험요인)\s*[:：]',value)
                        and source_unit_complete(value) and criterion not in chosen):
                    chosen.append(criterion)
        if goal == "method" and start and source_unit_complete(units[start - 1]):
            previous = units[start - 1]
            if (not QUALIFICATION.match(previous) and any(word in previous for word in ("통합", "인터넷", "예약"))
                    and len(previous) + len(units[start]) < 300):
                chosen.insert(0, previous)
        # Keep adjacent exceptions whole; never shorten away a condition.
        for unit in units[start + 1:]:
            if QUALIFICATION.match(unit):
                if unit not in chosen:
                    chosen.append(unit)
            else:
                break
        if goal == "method" and "무상" in topics:
            # A free-service exclusion may follow its product table rather
            # than the application field. Include only an explicit exclusion
            # naming the same subject, never another product's exceptions.
            subjects = topics - {"무상", "수거", "보건소"}
            for unit in units[start + 1:start + 81]:
                if (QUALIFICATION.match(unit) and unit not in chosen
                        and any(word in compact(unit) for word in subjects)
                        and any(word in unit for word in ("제외", "않음", "불가", "유상", "부담"))):
                    chosen.append(unit)
        if any(not source_unit_complete(unit) for unit in chosen):
            continue
        # Validate the actual chosen facts and their owning heading. A topic
        # elsewhere on the same page cannot validate an unrelated fallback.
        from chatbot.source_hierarchy import heading_path
        local_keywords = keywords - {'보건소','구청'}
        # In a named program, '임산부' asks about its audience; source rows may
        # explicitly split that audience into 임신부·출산부·수유부. The complete
        # page has already established the program and requested topic above.
        named_programs = local_keywords.intersection(SERVICE_NAMES) - {'임산부'}
        if '임산부' in local_keywords and any(name in compact(title) for name in named_programs):
            local_keywords = local_keywords - {'임산부'}
        if local_keywords and not topic_support({
                'content':' '.join(chosen) + ' ' + heading_path(units,start),
                'metadata':{'title':title}}, local_keywords)[0]:
            continue
        # A fact about support ages cannot drop its complete requirements just
        # because a nearby method/marketing unit won the fallback ranking.
        for pos in [i for i,u in enumerate(units) if u in chosen]:
            if re.search(r'아래\s*(?:요건|조건).*모두',units[pos]):
                chosen = [units[i] for i in condition_indices(units,[units.index(u) for u in chosen])]
        answer = "\n".join("- " + line for line in chosen)
        if len(answer) <= MAX_BRIEF_LENGTH:
            return answer
    return None


def scope_question(query: str, body: str) -> dict:
    fields = [("신청 방법", ("신청", "접수", "예약")), ("대상 조건", ("대상", "자격", "조건")),
              ("비용", ("수수료", "요금", "비용")), ("운영시간", ("시간", "일정")),
              ("준비 서류", ("서류", "준비"))]
    choices = [label for label, words in fields if any(word in body for word in words)][:3]
    # A clear request must not be sent back to choose the same field again.
    goal = answer_goal(query)
    if goal and any(line.startswith('#') for line in body.splitlines()):
        label = {'hours':'운영시간','location':'이용 장소','eligibility':'대상 조건',
                 'documents':'준비 서류','cost':'비용·감면 조건','schedule':'일정',
                 'method':'이용 방법','services':'이용 가능한 서비스','definition':'제도 설명',
                 'precautions':'행동요령','necessity':'서류 제출 여부'}.get(goal,'요청하신 항목')
        return {"answer": f"관련 공식 자료는 찾았지만, {label}을 정확히 안내할 근거를 확인하지 못했습니다. 출처의 담당 부서에서 해당 항목을 확인해 주세요.",
            "answer_details": "", "is_clarification": False, "degraded": True,
            "suggested_questions": []}
    if goal:
        return {"answer":"확인된 원문만으로는 요청 항목을 명확히 안내하기 어렵습니다. 어떤 신청 유형이나 대상에 관한 문의인지 조금 더 알려주시겠어요?",
                "answer_details":"", "is_clarification":True,"suggested_questions":[],"reply_terms":["유형","대상"]}
    if not choices:
        choices = ["대상이나 사업명"]
    answer = "안내 범위를 좁혀볼게요. **" + "·".join(choices) + "** 중 어떤 내용을 확인하시겠어요?"
    base = re.sub(r"알려(?:주세요|줘)?|어떻게.*$", "", query).strip().rstrip("?!")
    return {"answer": answer, "answer_details": "", "is_clarification": True,
            "suggested_questions": [f"{base} {choice} 알려줘" for choice in choices],
            "reply_terms": [word for _, words in fields for word in words]}


def concise_source_answer(query: str, original_answer: str, documents: list[dict], keywords: set[str]) -> dict:
    lines = source_lines(original_answer)
    body = "\n".join(lines)
    url = str((documents[0].get("metadata") or {}).get("url") or "") if documents else ""
    if documents:
        from chatbot.reference_answers import reference_answer
        reference = reference_answer(query, documents[0], body, keywords, original_answer)
        if reference:
            return reference
    answer = vaccination_place_brief(query, url, lines)
    if (asks_location(query) and is_vaccination_query(query)
            and any(mid in url for mid in ('mId=0203020000', 'mId=0203020100')) and not answer):
        return scope_question(query, body)
    if documents and documents[0].get("metadata", {}).get("category") == "staff_directory":
        meta = documents[0]['metadata']
        answer = f"**{meta.get('department', '')}** · **{meta.get('contact', '')}**\n{meta.get('title', '')}"
    if "mId=0104020000" in url:
        answer = _passport(query, body)
    elif "mId=0403080000" in url:
        answer = _parking(query, body)
    elif "대형폐기물" in compact(body) and "대형폐기물" in compact(query):
        answer = _waste(query, body)
    if not answer:
        answer = _extract_brief(query, lines, keywords, str((documents[0].get("metadata") or {}).get("title") or "") if documents else "")
    if not answer:
        return scope_question(query, body)
    audience = next((line.removeprefix('- ').strip() for line in answer.splitlines()
                     if SCOPE_FIELD.match(line.removeprefix('- ').strip())), None)
    course_scope = course_scope_result(query, audience)
    if course_scope:
        if course_scope['is_clarification']:
            return course_scope
        answer = course_scope['answer']
    if answer_goal(query) in ('location', 'hours', 'schedule') and re.search(r'예정|미정|잠정|추후', answer):
        answer = "공식 자료에 예정·미정으로 표시되어 있어 현재 확정 정보는 확인되지 않습니다.\n" + answer
    meta = (documents[0].get("metadata") or {}) if documents else {}
    title = str(meta.get("title") or "")
    if title and not any(word in compact(answer) for word in substantive_keywords(keywords)):
        answer = f"**{title}** 안내:\n" + answer
    elif title and answer_goal(query) == "method" and compact(title) not in compact(answer):
        # A channel name is essential when the actual instruction only says
        # 'apply online'. Display the verified page title beside that field.
        answer = f"**{title}** 안내:\n" + answer
    if (not course_scope and meta.get('category') != 'staff_directory'
            and meta.get('source_type') != 'official_report'
            and not re.search(r'예정|미정|잠정|추후', answer)):
        from chatbot.answer_enrichment import enrich_answer
        answer = enrich_answer(query, answer, body, keywords, title)
    if len(answer) > MAX_BRIEF_LENGTH:
        return scope_question(query, body)
    if meta.get("source_type") == "official_report":
        answer = f"자료 기준: {meta.get('data_period', '미상')}\n\n" + answer
    return {"answer": answer, "answer_details": original_answer, "is_clarification": False,
            "suggested_questions": []}
