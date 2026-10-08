"""외부 API나 DB 없이 실행 가능한 대화 UX 보조 로직."""

import re
from chatbot.vaccination import needs_vaccine_kind, vaccine_kind
from chatbot.question_intent import asks_location, location_subject
from chatbot.query_subject import AREA_PATTERN
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


def resolve_clarification_reply(message: str, pending: dict | None) -> str:
    """Only attach a short answer to the specific question we just asked."""
    if not pending:
        return message
    current = re.sub(r"\s+", "", message)
    if pending.get('affirmative_context') and current.rstrip('.!?') in ('네', '예', '응', '맞아', '맞아요'):
        return pending['query'] + ' ' + pending['affirmative_context']
    if pending.get('negative_context') and current.rstrip('.!?') in ('아니', '아니요', '아니야'):
        return pending['query'] + ' ' + pending['negative_context']
    if message in pending.get("suggested_questions", []):
        return message  # Buttons already contain a complete, narrowed question.
    previous = re.sub(r"\s+", "", pending.get("query", ""))
    for topic in ("여권", "보건증", "폐기물", "복지", "주차", "화재", "출산", "건축", "세금", "등본"):
        if topic in current and topic not in previous:
            return message
    # A named vaccine plus a new question goal starts that question; a bare
    # type such as '독감' still answers our pending place clarification.
    if vaccine_kind(message):
        for goal in ('비용', '수수료', '얼마', '운영시간', '접종시간', '시기', '대상', '조건', '준비물', '서류'):
            if goal in current and goal not in previous:
                return message
    if len(current) <= 35 and any(term in current for term in pending.get("reply_terms", [])):
        return pending["query"] + " " + message
    return message


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


def build_clarification(user_message: str) -> dict | None:
    """근거 없는 포괄 답변 대신 사용자 상황을 좁히는 결정적 역질문을 만든다."""
    compact = re.sub(r"[\s?!.,]", "", user_message or "")

    if needs_vaccine_kind(user_message):
        return clarification_question(
            "어떤 백신을 접종하시려나요? **독감·폐렴구균·B형간염** 등 종류를 알려주세요. 백신마다 접종 장소가 달라요.",
            ['독감 접종 장소 알려줘', '폐렴구균 접종 장소 알려줘', 'B형간염 접종 장소 알려줘'],
            ['독감', '인플루엔자', '폐렴', '간염', '코로나', 'HPV', 'hpv', '유두종', '자궁경부암',
             '대상포진', '파상풍', '장티푸스', 'BCG', 'bcg', '홍역', '뇌염', '수두', '로타', '황열', '콜레라', 'RSV', 'rsv'])

    # One missing condition per turn. Suggestions are questions, not promises
    # that a particular service or eligibility rule exists.
    if "여권" in compact:
        adult = any(word in compact for word in ("성인", "어른", "18세이상"))
        minor = any(word in compact for word in ("미성년", "아이", "자녀", "18세미만"))
        new = any(word in compact for word in ("신규", "처음", "새로"))
        renew = "재발급" in compact
        docs = any(word in compact for word in ("준비", "서류", "구비"))
        goal = bool(answer_goal(user_message)) or any(word in compact for word in ("준비", "서류", "구비", "수수료", "비용", "얼마", "기간", "며칠", "시간", "장소", "어디", "사진", "전화", "담당", "번호"))
        if docs and not (adult or minor):
            return clarification_question("여권을 신청하는 분이 **성인**인가요, **만 18세 미만**인가요?",
                ["성인 신규 여권 준비물 알려줘", "성인 여권 재발급 준비물 알려줘", "미성년자 여권 준비물 알려줘"],
                ["성인", "어른", "미성년", "아이", "자녀", "18세"])
        if docs and adult and not (new or renew):
            return clarification_question("여권을 **처음 발급**받으시나요, **재발급**받으시나요?",
                ["성인 신규 여권 준비물 알려줘", "성인 여권 재발급 준비물 알려줘"], ["신규", "처음", "새로", "재발급"])
        if docs and minor and not any(word in compact for word in ('부모', '친권자', '법정대리인', '본인', '친족')):
            return clarification_question("미성년자 여권은 **누가 신청**하시나요? 부모·본인·친족 대리인을 구분해 주세요.",
                ["부모가 미성년자 여권 신청할 때 준비물", "미성년자 본인이 여권 신청할 때 준비물", "친족이 미성년자 여권 대리 신청할 때 준비물"],
                ['부모', '친권자', '법정대리인', '본인', '친족'])
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
        if not any(word in compact for word in ("배출", "버리", "신청", "접수", "방법", "수수료", "비용", "가격", "얼마", "전화", "담당")):
            return clarification_question("대형폐기물의 **배출 방법**과 **수수료** 중 무엇이 궁금하신가요?",
                ["대형폐기물 배출 방법 알려줘", "대형폐기물 수수료 알려줘"], ["배출", "버리", "방법", "수수료", "비용", "가격"])

    if "무인민원발급기" in compact and not any(word in compact for word in ("위치", "어디", "장소", "시간", "수수료", "비용", "얼마", "서류", "등본", "전화", "담당")):
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
    if len(compact) > 22 or not any(pattern in compact for pattern in vague_patterns):
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
    is_follow_up = (
        len(compact) <= 16 and (
            compact.startswith(("그건", "그럼", "그거", "그것", "그러면", "그경우"))
            or re.search(r"(은요|는요|도요|그때는|수수료는|비용은)[?？]?$", compact)
        )
    )
    if not is_follow_up:
        return current
    recent_user_messages = [
        (message.get("search_query") or message.get("content") or "").strip()
        for message in (history or [])[-4:]
        if message.get("role") == "user" and (message.get("content") or "").strip()
    ]
    previous = recent_user_messages[-1] if recent_user_messages else ""
    if any(word in current for word in ("수수료", "비용", "얼마")):
        previous = re.sub(r"준비물|준비서류|구비서류|서류|준비|기간|며칠", "", previous)
        previous = location_subject(previous)
    elif any(word in current for word in ("기간", "시간", "며칠")):
        previous = re.sub(r"준비물|준비서류|구비서류|서류|준비|수수료|비용|얼마", "", previous)
        previous = location_subject(previous)
    elif asks_location(current):
        previous = re.sub(r"준비물|준비서류|구비서류|서류|준비|기간|시간|며칠|수수료|비용|얼마", "", previous)
    return (previous + " " + current).strip()
