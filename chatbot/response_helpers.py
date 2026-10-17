"""외부 API나 DB 없이 실행 가능한 대화 UX 보조 로직."""

import re
from chatbot.vaccination import needs_vaccine_kind, vaccine_kind
from chatbot.question_intent import asks_location, location_subject
from chatbot.query_subject import AREA_PATTERN, SERVICE_NAMES, compact as topic_compact, service_names
from chatbot.answer_goal import answer_goal


def _broad_support_request(message: str) -> bool:
    """Ask a welfare scope question only when no service name remains."""
    text = AREA_PATTERN.sub("", message or "")
    text = re.sub(r"[\s?!.,·]", "", text)
    text = re.sub(r"어르신|노인|장애인|아동|보육|청년|주민|구민", "", text)
    text = re.sub(r"\d+세(?:이상|이하|미만)?", "", text)
    text = re.sub(r"지원금|복지|지원|혜택|서비스|제도|사업|신청|방법|조건|대상|자격|도움|필요", "", text)
    text = re.sub(r"알려(?:주세요|줘)?|받고싶(?:어요|어)?|받을수|받으려면|있(?:나요|어요|어)|"
        r"어떤(?:거|것)?|무슨|뭐가|어떻게|하고싶(?:어요|어)?|이용|찾고|싶(?:어요|어)?", "", text)
    text = re.sub(r"에서|에게|으로|에는|에|은|는|이|가|을|를|의|요", "", text)
    return not text


def clarification_question(answer: str, questions: list[str], reply_terms: list[str]) -> dict:
    return {"answer": answer, "suggested_questions": questions[:3], "reply_terms": reply_terms}


def _scope_confirmation(message: str) -> tuple[str | None, str]:
    """Parse a reply to a yes/no scope question, never a substring in a question.

    Only a standalone acknowledgement or one followed by an elided field is
    accepted. New services, uncertainty and negated confirmations stay intact.
    """
    text = re.sub(r'[\s,.!?。？!]', '', message)
    if re.search(r'모르|아마|글쎄|맞는지|맞나요|맞을까|아닌지', text):
        return None, ''
    negative = r'(?:아니(?:요|야|에요)?|아냐|아닌데(?:요)?|안맞아(?:요)?|맞지않아(?:요)?)'
    positive = r'(?:(?:어|아)?(?:네네|네|예|응|넵)|(?:어|아)?(?:그교육|그대상|해당대상|그거)?맞(?:아요|아|습니다|으니까)|그래(?:요)?)'
    for value, pattern in (('negative', negative), ('affirmative', positive)):
        match = re.match(r'^(?:' + pattern + r')+', text)
        if not match:
            continue
        tail = text[match.end():]
        if not tail or is_field_only_question(tail):
            return value, tail
        if value == 'negative' and re.fullmatch(r'일반(?:주민|구민)(?:이야|이에요|입니다)?', tail):
            return value, ''
    return None, ''


def _scoped_query(query: str, scope: str, field: str = '') -> str:
    # Keep the confirmed audience as a separate profile when the next turn
    # changes only the requested field. This is internal search context.
    scoped = f'{query} (확인대상: {scope})'
    if field:
        return build_contextual_search_query(field, [{'role': 'user', 'content': query, 'search_query': scoped}])
    return scoped


def resolve_clarification_reply(message: str, pending: dict | None) -> str:
    """Only attach a short answer to the specific question we just asked."""
    if not pending:
        return message
    from chatbot.passport_documents import merge_applicant_followup
    current = re.sub(r"\s+", "", message)
    previous = re.sub(r"\s+", "", pending.get("query", ""))
    # A complete new subject takes precedence even if it starts with "네".
    if pending.get('affirmative_context'):
        names, old_names = service_names(message), service_names(pending.get('query', ''))
        if any(not any(n in old or old in n for old in old_names) for n in names):
            return message
        for topic in ("여권", "보건증", "폐기물", "복지", "주차", "화재", "출산", "건축", "세금", "등본", "보건소"):
            if topic in current and topic not in previous:
                return message
    choices = pending.get('choice_contexts', {})
    if message in choices:
        return _scoped_query(pending['query'], choices[message])
    if pending.get('affirmative_context'):
        decision, field = _scope_confirmation(message)
        context = pending.get(f'{decision}_context') if decision else None
        if context:
            return _scoped_query(pending['query'], context, field)
        if re.fullmatch(r'(?:잘|그게)?(?:맞는지|해당하는지)?모르(?:겠어|겠어요|겠습니다|겠는데요)', current.rstrip('.!?')):
            return pending['query']
    if ('여권' in pending.get('query','') and '세' in pending.get('reply_terms',[]) and
            len(current) <= 40 and re.match(r'^(?:만)?\d{1,2}(?:세|살)', current)):
        return merge_applicant_followup(pending['query'], message)
    if message in pending.get("suggested_questions", []):
        return message  # Buttons already contain a complete, narrowed question.
    if (len(current) <= 25 and not answer_goal(message)
            and any(term in current for term in pending.get('reply_terms',[]))):
        return merge_applicant_followup(pending['query'], message)
    for topic in ("여권", "보건증", "폐기물", "복지", "주차", "화재", "출산", "건축", "세금", "등본"):
        if topic in current and topic not in previous:
            return message
    # A named vaccine plus a new question goal starts that question; a bare
    # type such as '독감' still answers our pending place clarification.
    if vaccine_kind(message):
        for goal in ('비용', '수수료', '얼마', '운영시간', '접종시간', '시기', '대상', '조건', '준비물', '서류'):
            if goal in current and goal not in previous:
                return message
    if len(current) <= 60 and any(term in current for term in pending.get("reply_terms", [])):
        return merge_applicant_followup(pending['query'], message)
    # A user may change the applicant instead of answering the requested role.
    # Reuse ordinary follow-up routing, including its new-service boundary.
    return build_contextual_search_query(message, [
        {'role': 'user', 'content': pending.get('query', '')}])


def is_obviously_out_of_domain(user_message: str) -> bool:
    """행정 문서의 우연한 단어 겹침으로 LLM이 호출되는 명백한 비행정 질문을 차단한다."""
    compact = re.sub(r"\s+", "", (user_message or "").lower())
    patterns = (
        r"(주가|주식|코인|비트코인|가상화폐).*(예측|추천|매수|매도|전망)",
        r"(예측|추천|매수|매도|전망).*(주가|주식|코인|비트코인|가상화폐)",
        r"로또.*(번호|추천|예측)",
        r"(오늘|내일).*(축구|야구|농구).*(승부|점수|결과).*(예측|추천)",
    )
    return any(re.search(pattern, compact) for pattern in patterns)


def unavailable_capability(message: str) -> dict | None:
    text = topic_compact(message)
    if re.search(r'주차장|주차면',text) and re.search(r'빈자리|빈공간|(?:남은|잔여|여유)(?:주차)?(?:칸|자리|공간|면)|잔여|몇대가능|비어|비었|빈주차|자리수',text) and re.search(r'지금|현재|실시간|오늘',text):
        answer = '현재 상담에는 **실시간 주차 잔여면수 조회 기능이 없습니다.** 주차장의 전체 주차면수를 현재 빈자리 수로 안내할 수는 없습니다.'
        reason = 'live_data_unavailable'
    elif (re.search(r'지금|현재|실시간',text) and
          re.search(r'대기.{0,8}(?:인원|사람|몇명)|(?:남은|잔여).{0,8}(?:인원|자리|정원)',text)):
        answer = '현재 상담에는 **실시간 대기 인원·남은 접수 인원을 조회하는 기능이 없습니다.** 안내문의 모집 정원이나 대기 가능 여부를 현재 인원으로 바꾸어 안내할 수는 없습니다.'
        reason = 'live_data_unavailable'
    elif re.search(r'대신|알아서|너가|네가',text) and re.search(r'신청접수해|신청해줘|예약해줘|접수해줘',text):
        answer = '챗봇은 **신청·접수를 대신 실행할 수 없습니다.** 필요한 서류와 공식 신청 방법은 안내할 수 있어요.'
        if not service_names(message):
            answer += ' 어떤 업무를 신청하시나요?'
        reason = 'action_not_supported'
    else:
        return None
    return {'answer':answer,'sources':[],'is_clarification':False,'degraded':True,'degraded_reason':reason,
            'evidence':{'status':'insufficient','label':'실행·조회 기능 확인 필요','official_source_count':0},'suggested_questions':[]}


def is_field_only_question(message: str) -> bool:
    """Recognize elided fields without treating a new service as a follow-up."""
    text = re.sub(r'[\s?!.,？]', '', message or '')
    text = re.sub(r'^(?:그럼|그러면|그건|그거|관련)', '', text)
    text = re.sub(r'(?:은|는)?어떻게(?:하나요|해요|해|받아요|받아)[?？]?$', '방법', text)
    text = re.sub(r'(?:좀)?(?:알려(?:줘|주세요)|설명해줘|보고싶(?:어|어요)|보여(?:줘|주세요)|확인하고싶(?:어|어요)|궁금(?:해|해요))$', '', text)
    fields = r'현황도|현황|노선도|노선|지도|위치|주소|장소|시간|일정|기간|비용|수수료|준비물|서류|대상|자격|조건|참여방법|신청방법|이용방법|신청절차|발급절차|신청|접수|방법'
    return bool(text and re.fullmatch(r'(?:(?:' + fields + r')(?:과|와|이랑|랑|하고|및)?)+(?:은|는|을|를|도|가|이|요|좀)*', text))


def build_clarification(user_message: str) -> dict | None:
    """근거 없는 포괄 답변 대신 사용자 상황을 좁히는 결정적 역질문을 만든다."""
    from chatbot.query_subject import interpret_query
    user_message = interpret_query(user_message)
    compact = re.sub(r"[\s?!.,]", "", user_message or "")
    if is_field_only_question(user_message):
        return clarification_question('**어떤 시설이나 업무**에 관한 안내가 필요하신가요?',
            [], ['시설','업무','자전거','주차','보건소','주민등록','소방'])
    identity = topic_compact(user_message)
    if ('건강진단결과서' in identity and re.search(r'발급|방법|어떻게|받', identity)
            and not re.search(r'처음|검사|재발급|재출력|다시|인터넷|온라인|준비물|서류|비용|수수료|시간|기간|장소|어디', identity)):
        return clarification_question('**처음 검사를 받으려는 건가요**, 아니면 **검사 후 결과서를 발급**받으려는 건가요?',
            ['보건증 처음 검사받는 방법 알려줘', '보건증 검사 후 결과서 발급 방법 알려줘'],
            ['처음','검사','재발급','재출력','다시'])
    if ('주민등록증' in identity and re.search(r'발급|절차|만들', identity)
            and not re.search(r'재발급|신규|처음|분실|잃어|훼손|변경|모바일|사진|수수료|비용', identity)):
        return clarification_question('주민등록증을 **처음 발급**받으시나요, 아니면 **재발급**받으시나요?',
            ['주민등록증 처음 발급 절차 알려줘', '주민등록증 재발급 절차 알려줘'],
            ['처음','신규','재발급','분실','잃어','훼손'])
    if '통합예약' in compact and re.search(r'취소|변경',compact) and not re.search(r'체험관|축구|테니스|체육|도서관|강좌|프로그램|정비창|문화|대관',compact):
        return clarification_question('예약한 시설·프로그램에 따라 취소 방법이 다릅니다. **어떤 시설이나 프로그램을 예약하셨나요?**',
            [], ['체험관','축구','테니스','체육','도서관','강좌','프로그램','정비창','문화','대관'])
    if ('쓰레기' in compact and re.search(r'아무때|낮|배출시간',compact)
            and not any(kind in compact for kind in ('일반쓰레기','종량제','음식물','재활용','분리수거'))):
        return clarification_question('**일반쓰레기·음식물·재활용 중 무엇을 배출**하시나요? 종류에 맞는 시간·방법을 확인하겠습니다.',
            ['일반쓰레기 배출시간 알려줘','음식물쓰레기 배출시간 알려줘','재활용품 배출시간 알려줘'],
            ['일반','종량제','음식물','재활용','분리수거'])
    if re.search(r'가구.*(?:버리|배출)', compact) and any(w in compact for w in ('비용','수수료','얼마')) and not re.search(r'침대|소파|책상|의자|장롱',compact):
        return clarification_question('버릴 가구의 **품목과 크기**를 알려주세요. 수수료는 품목·규격별로 다릅니다.',
            ['2인용 소파 배출 수수료','일반침대 1인용 배출 수수료'], ['소파','침대','책상','의자','장롱'])
    if re.search(r'생활비.*지원', compact) and not re.search(r'실직|질병|폐업|긴급복지|기초생활|연금',compact):
        return clarification_question('생활비 지원은 상황에 따라 달라요. **실직·질병·폐업 등으로 갑자기 생계가 어려워지셨나요?**',
            ['실직한 경우 긴급복지 생계지원 신청 방법'], ['실직','질병','폐업','소득','갑자기'])
    if '민방위' in compact and re.search(r'대피소|대피시설',compact) and not re.search(r'(?:괴정|당리|하단|신평|장림|다대|구평|감천)[1-4]?동',compact):
        return clarification_question('**어느 동 근처의 대피시설**을 찾으시나요? 동 이름을 알려주세요.',
            ['장림1동 민방위 대피시설 위치'], ['괴정','당리','하단','신평','장림','다대','구평','감천'])
    if (any(w in compact for w in ('수수료','발급비','민원서류')) and any(w in compact for w in ('면제','공짜','전부무료')) and not any(w in compact for w in
            ('등본','초본','인감','서명','가족관계','출입국','과세증명','공시지가'))):
        return clarification_question('어떤 민원이나 서류의 수수료인가요? **등·초본·인감증명서 등 종류**에 따라 면제 조건이 달라요.',
            ['기초생활수급자 주민등록등본 수수료 면제 조건','한부모가족 인감증명서 수수료 면제 조건'],
            ['등본','초본','인감','가족관계','출입국','과세','신고','허가'])

    from chatbot.official_faq import required_faq_ids
    if required_faq_ids(user_message) == {1, 2}:
        return None
    if re.fullmatch(r"(?:담당자|담당부서)?(?:전화번호|연락처)(?:알려줘|알려주세요)?", compact):
        return clarification_question('어떤 민원이나 업무의 연락처가 필요한가요?',
            ['여권 담당 부서 연락처', '대형폐기물 담당 부서 연락처'], ['여권', '폐기물', '민원처리', '단속'])
    if re.fullmatch(r'(?:통합)?예약(?:하고싶어요|하고싶어|안내해줘|알려줘|방법알려줘|어떻게해|하고싶은데어디서해)?', compact):
        return clarification_question('어떤 예약이 필요한가요? **교육·체험 프로그램 또는 시설명**을 알려주세요.',
            ['작은도서관 프로그램 예약 방법 알려줘', '소방특화 들락날락 체험 예약 방법 알려줘'],
            ['도서관', '들락날락', '소방', '시설', '교육', '체험'])

    if needs_vaccine_kind(user_message):
        return clarification_question(
            "어떤 백신을 접종하시려나요? **독감·폐렴구균·B형간염** 등 종류를 알려주세요. 백신마다 접종 장소가 달라요.",
            ['독감 접종 장소 알려줘', '폐렴구균 접종 장소 알려줘', 'B형간염 접종 장소 알려줘'],
            ['독감', '인플루엔자', '폐렴', '간염', '코로나', 'HPV', 'hpv', '유두종', '자궁경부암',
             '대상포진', '파상풍', '장티푸스', 'BCG', 'bcg', '홍역', '뇌염', '수두', '로타', '황열', '콜레라', 'RSV', 'rsv'])

    if (re.search(r'모든|전부',compact) and re.search(r'예방접종|백신',compact)
            and not vaccine_kind(user_message) and re.search(r'지원|무료|끝|나이|세',compact)):
        return clarification_question('백신마다 지원 연령이 다릅니다. **어떤 백신의 지원 여부**가 궁금하신가요?',
            [], ['독감','인플루엔자','폐렴','간염','HPV','hpv','유두종','자궁경부암','대상포진','파상풍','수두','로타'])

    # One missing condition per turn. Suggestions are questions, not promises
    # that a particular service or eligibility rule exists.
    if "여권" in compact:
        from chatbot.passport_documents import applicant_age, applicant_role, document_request
        age = applicant_age(user_message)
        adult, minor = age == 'adult', age == 'minor'
        new = any(word in compact for word in ("신규", "처음", "새로"))
        renew = "재발급" in compact
        docs = document_request(user_message)
        goal = bool(answer_goal(user_message)) or any(word in compact for word in ("준비", "서류", "구비", "수수료", "비용", "얼마", "기간", "며칠", "시간", "장소", "어디", "사진", "전화", "담당", "번호"))
        if docs and not (adult or minor):
            return clarification_question("여권을 신청하는 분이 **성인**인가요, **만 18세 미만**인가요?",
                ["성인 신규 여권 준비물 알려줘", "성인 여권 재발급 준비물 알려줘", "미성년자 여권 준비물 알려줘"],
                ["성인", "어른", "미성년", "아이", "자녀", "세", "부모", "본인", "친족", "직접", "엄마", "아빠"])
        if docs and adult and not (new or renew):
            return clarification_question("여권을 **처음 발급**받으시나요, **재발급**받으시나요?",
                ["성인 신규 여권 준비물 알려줘", "성인 여권 재발급 준비물 알려줘"], ["신규", "처음", "새로", "재발급"])
        if docs and minor and applicant_role(user_message) is None:
            return clarification_question("미성년자 여권은 **누가 신청**하시나요? 부모·본인·친족 대리인을 구분해 주세요.",
                ["부모가 미성년자 여권 신청할 때 준비물", "미성년자 본인이 여권 신청할 때 준비물", "친족이 미성년자 여권 대리 신청할 때 준비물"],
                ['부모', '친권자', '법정대리인', '본인', '친족', '직접', '엄마', '아빠'])
        if any(word in compact for word in ("수수료", "비용", "얼마")) and not (adult and '10년' in compact and any(word in compact for word in ('58면', '26면'))):
            return clarification_question("여권 수수료는 **연령·유효기간·면수**에 따라 달라요. 어떤 여권을 신청하시나요?",
                ["성인 10년 58면 여권 수수료 알려줘", "성인 10년 26면 여권 수수료 알려줘"],
                ["성인", "어른", "10년", "58면", "26면", "미성년", "18세"])
        if not goal:
            return clarification_question("여권의 **준비 서류·수수료·발급 기간** 중 무엇이 궁금하신가요?",
                ["여권 준비 서류 알려줘", "여권 발급 수수료 알려줘", "여권 발급 기간 알려줘"], ["준비", "서류", "수수료", "비용", "기간", "며칠"])

    if any(word in compact for word in ("대형폐기물", "대형쓰레기")):
        item = any(word in compact for word in ("침대", "매트리스", "소파", "책상", "의자", "장롱", "냉장고", "세탁기", "텔레비", "에어컨"))
        fee = any(word in compact for word in ("수수료", "비용", "가격", "얼마"))
        if fee and not item:
            return clarification_question("어떤 물품을 버리시나요? **품목과 크기**에 따라 수수료가 달라요.",
                ["일반침대 1인용 수수료 알려줘", "일반침대 2인용 수수료 알려줘", "소파 배출 수수료 알려줘"],
                ["침대", "매트리스", "소파", "책상", "의자", "장롱", "냉장고", "세탁기", "텔레비", "에어컨"])
        if not answer_goal(user_message) and not any(word in compact for word in ("배출", "버리", "신청", "접수", "방법", "수수료", "비용", "가격", "얼마", "전화", "담당")):
            return clarification_question("대형폐기물의 **배출 방법**과 **수수료** 중 무엇이 궁금하신가요?",
                ["대형폐기물 배출 방법 알려줘", "대형폐기물 수수료 알려줘"], ["배출", "버리", "방법", "수수료", "비용", "가격"])

    if "무인민원발급기" in compact and not any(word in compact for word in ("위치", "어디", "장소", "시간", "수수료", "비용", "얼마", "서류", "등본", "증명", "전화", "담당")):
        return clarification_question("무인민원발급기의 **위치·운영시간·수수료** 중 무엇이 궁금하신가요?",
            ["무인민원발급기 위치 알려줘", "무인민원발급기 운영시간 알려줘", "무인민원발급기 수수료 알려줘"], ["위치", "어디", "시간", "수수료", "비용"])

    specific_support = any(word in compact for word in ("출산", "양육", "아동수당", "부모급여", "기초연금", "기초생활", "장애인연금", "장애수당", "활동지원", "장학", "일자리", "생활비", "돌봄"))
    if (("복지" in compact or "지원" in compact or "혜택" in compact)
            and not specific_support and _broad_support_request(user_message)
            and not any(word in compact for word in ("담당", "전화", "부서", "연락"))):
        audience = next((word for word in ("어르신", "노인", "장애인", "아동", "보육", "청년") if word in compact), "")
        if not audience:
            return clarification_question("**누구를 위한 지원**을 찾으시나요? 어르신·아동·장애인 등 대상을 알려주세요.",
                ["어르신 복지 지원 알려줘", "아동·보육 지원 알려줘", "장애인 복지 지원 알려줘"], ["어르신", "노인", "아동", "보육", "장애인", "청년"])
        return clarification_question(f"{audience} 지원 중 **생활비·돌봄·일자리** 등 어떤 도움이 필요하신가요?",
            [f"{audience} 생활비 지원 조건 알려줘", f"{audience} 돌봄 지원 신청 방법 알려줘", f"{audience} 일자리 신청 방법 알려줘"], ["생활비", "돌봄", "일자리", "연금", "수당"])

    if compact in ("민원", "민원알려줘", "민원안내해줘", "서류발급알려줘", "증명서발급알려줘"):
        return clarification_question("**어떤 민원이나 서류**가 필요하신가요?",
            ["주민등록등본 발급 방법 알려줘", "여권 준비 서류 알려줘", "보건증 발급 방법 알려줘"], ["등본", "초본", "여권", "보건증", "증명"])

    # 대형폐기물 수수료는 종류·규격에 따라 달라진다. 특히 '침대'만으로는
    # 돌/일반, 1/2인용, 매트리스 단독 여부를 구분할 수 없어 최고 금액을
    # 단정하기 쉽다. 검색/LLM 전에 필요한 규격을 먼저 확인한다.
    asks_fee = any(keyword in compact for keyword in ("수수료", "비용", "가격", "얼마"))
    if asks_fee and re.search(r'소파|쇼파',compact) and not re.search(r'\d+인용|스툴|카우치',compact):
        return clarification_question('소파 수수료를 확인할 수 있도록 **몇 인용인지 또는 크기**를 알려주세요.',
            [], ['1인용','2인용','3인용','4인용','스툴','카우치'])
    mentions_bed = "침대" in compact or "매트리스" in compact
    has_bed_type = any(keyword in compact for keyword in ("돌침대", "일반", "매트리스", "라텍스"))
    if asks_fee and mentions_bed and not has_bed_type:
        return clarification_question("침대 수수료는 **종류와 규격**에 따라 달라요. 일반침대·돌침대·매트리스 중 어떤 물품인가요?",
            ["일반침대 1인용 수수료 알려줘", "돌침대 배출 수수료 알려줘", "매트리스만 배출할 때 수수료 알려줘"],
            ["일반", "돌침대", "매트리스", "1인용", "2인용", "싱글", "더블", "퀸", "킹"])
    if asks_fee and mentions_bed and not any(word in compact for word in ("1인용", "2인용", "싱글", "더블", "퀸", "킹")):
        kind = '돌침대' if '돌침대' in compact else '매트리스' if '매트리스' in compact else '일반침대'
        return clarification_question("**1인용인가요, 2인용인가요?** 물품 크기를 알려주세요.",
            [f"{kind} 1인용 수수료 알려줘", f"{kind} 2인용 수수료 알려줘"], ["1인용", "2인용", "싱글", "더블", "퀸", "킹"])

    vague_patterns = (
        "지원받고싶", "혜택알려", "신청하고싶", "도와줘", "도움받고싶",
        "어디에문의", "뭘해야", "무슨지원",
    )
    if (len(compact) > 22 or not any(pattern in compact for pattern in vague_patterns)
            or any(name in topic_compact(user_message) for name in SERVICE_NAMES)):
        return None

    return {
        "answer": (
            "어떤 분야의 안내가 필요한지 한 가지만 알려주세요. "
            "대상이나 상황을 함께 적으면 공식 자료에서 더 정확히 찾을 수 있습니다."
        ),
        "suggested_questions": [
            "어르신 복지 지원이 궁금해요",
            "아동·보육 지원이 궁금해요",
            "장애인 복지 지원이 궁금해요",
        ],
    }


def build_suggested_questions(user_message: str, sources: list[dict]) -> list[str]:
    """현재 답변과 자연스럽게 이어지는 행정 질문을 최대 3개 제안한다."""
    query = (user_message or "").lower()
    suggestions: list[str] = []
    topic_suggestions = [
        (("쓰레기", "폐기물", "재활용"), ["대형 폐기물 배출 방법 알려줘", "재활용품 분리배출 방법 알려줘"]),
        (("복지", "지원", "수당", "보육"), ["복지 서비스 신청 방법 알려줘", "복지 담당 부서 연락처 알려줘"]),
        (("민원", "발급", "등본", "증명"), ["온라인 민원 발급 방법 알려줘", "무인민원발급기 위치 알려줘"]),
        (("도로", "주차", "교통"), ["도로 파손 신고 방법 알려줘", "교통 민원 담당 부서 알려줘"]),
    ]
    for keywords, candidates in topic_suggestions:
        if any(keyword in query for keyword in keywords):
            suggestions.extend(candidates)
            break

    for source in sources or []:
        department = (source.get("department") or "").strip()
        if department:
            suggestions.append(f"{department}에서 담당하는 업무 알려줘")
            break
    if any(source.get("attachments") for source in sources or []):
        suggestions.append("관련 첨부서류도 확인하고 싶어요")

    unique: list[str] = []
    for suggestion in suggestions:
        if suggestion not in unique and suggestion != user_message:
            unique.append(suggestion)
    return unique[:3]


def build_contextual_search_query(user_message: str, history: list[dict]) -> str:
    """생략된 후속 질문에만 직전 주제를 보충한다."""
    current = (user_message or "").strip()
    compact = re.sub(r"\s+", "", current)
    recent = [(m.get('search_query') or m.get('content') or '').strip()
              for m in history or [] if m.get('role') == 'user']
    previous_query = recent[-1] if recent else ''
    from chatbot.dialogue_profile import confirmed_profile
    decision, field = _scope_confirmation(current)
    if decision == 'affirmative':
        if not field and confirmed_profile(previous_query):
            return previous_query
        if field:
            # Without a remembered service, the resulting field-only query
            # asks for the topic instead of retrieving an arbitrary program.
            current = field
            compact = re.sub(r'\s+', '', current)
    generic = {'자전거','디지털','컴퓨터','냉장고','세탁기','구직','구인','건강검진','영유아'}
    names = service_names(current) - generic
    old_names = service_names(previous_query) - generic
    new_subject = any(not any(n in old or old in n for old in old_names) for n in names)
    if new_subject:
        return current
    # Bare fields can follow generic families too. The full-match language
    # check ensures "비상급수시설 지도" is a new topic, not a bicycle follow-up.
    field_follow_up = bool(previous_query and is_field_only_question(current))
    if field_follow_up:
        previous_names = service_names(previous_query)
        field_follow_up = bool(previous_names)
        old_names |= previous_names
    is_follow_up = (
        len(compact) <= 16 and (
            compact.startswith(("그건", "그럼", "그거", "그것", "그러면", "그경우"))
            or re.search(r"(은요|는요|도요|그때는|수수료는|비용은)[?？]?$", compact)
        )
    )
    # Elided field/condition questions need not start with '그럼'. Keep a
    # known service, but do not attach unrelated complete new questions.
    is_follow_up = is_follow_up or field_follow_up or bool(previous_query and old_names and len(compact) <= 60 and
        (not names or names <= old_names) and re.search(
            r'가져갈|등록장소|가입자|사업자등록|실직|소득이|몇급지|보상받|서류랑|주민등록등본이요',compact))
    from chatbot.passport_documents import applicant_age, merge_applicant_followup
    is_follow_up = is_follow_up or bool('여권' in previous_query and len(compact) <= 16
        and applicant_age(current) and not names)
    # A short reply to an actual contact choice can omit its work topic.
    # Complete questions such as '보건소 위치' keep their own topic.
    last_reply = next((str(m.get('content') or '') for m in reversed(history or [])
                       if m.get('role') == 'assistant'), '')
    if (len(compact) <= 45 and re.search(r'업무나 부서명|어떤 민원이나 업무',last_reply)
            and re.search(r'전화|번호|연락처',previous_query)
            and not re.search(r'여권|화재|비용|수수료|시간|기간|서류',compact)):
        return current + ' 담당 전화번호'
    if len(compact) <= 12 and any(word in last_reply for word in ('알려주세요', '어떤 업무', '어느 업무', '어느 부서')):
        is_follow_up = is_follow_up or compact in ('민원처리', '단속')
    if not is_follow_up:
        return current
    recent_user_messages = [
        (message.get("search_query") or message.get("content") or "").strip()
        for message in (history or [])[-4:]
        if message.get("role") == "user" and (message.get("content") or "").strip()
    ]
    previous = recent_user_messages[-1] if recent_user_messages else ""
    profile_reply = bool('여권' in previous and len(compact) <= 32
        and re.search(r'성인|어른|미성년|\d{1,2}(?:세|살)|신규|처음|재발급', compact)
        and not re.search(r'서류|준비|구비|챙|가져|방법|절차|어떻게|어디|언제|기간|시간|며칠|수수료|비용|얼마|대상|자격|조건|사진|규격|담당|연락|번호', compact))
    if answer_goal(current) and old_names and not profile_reply:
        # Carry the service and explicit profile, not the previous requested
        # field (e.g. automatic enrolment must not replace a benefit question).
        profile = re.findall(r'(?:괴정|당리|하단|신평|장림|다대|구평|감천)[1-4]?동|(?:만)?\d{1,2}세|성인|미성년자|부모|친족|신규|재발급',previous)
        scope = confirmed_profile(previous)
        if scope:
            profile.append(scope)
        subjects = sorted(old_names,key=len,reverse=True)
        if scope and re.search(r'교육|훈련|강좌', previous) and not any(re.search(r'교육|훈련|강좌', s) for s in subjects):
            subjects.append(re.search(r'교육|훈련|강좌', previous).group())
        if '인플루엔자' in subjects and '독감' in previous:
            subjects[subjects.index('인플루엔자')] = '독감'
        previous = ' '.join(subjects + profile)
    if any(word in current for word in ("수수료", "비용", "얼마")):
        previous = re.sub(r"준비물|준비서류|구비서류|서류|준비|기간|며칠", "", previous)
        previous = location_subject(previous)
    elif any(word in current for word in ("기간", "시간", "며칠")):
        previous = re.sub(r"준비물|준비서류|구비서류|서류|준비|수수료|비용|얼마", "", previous)
        previous = location_subject(previous)
    elif asks_location(current):
        previous = re.sub(r"준비물|준비서류|구비서류|서류|준비|기간|시간|며칠|수수료|비용|얼마", "", previous)
    if previous in current or previous == current:
        return current
    return merge_applicant_followup(previous, current)
