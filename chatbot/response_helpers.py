"""외부 API나 DB 없이 실행 가능한 대화 UX 보조 로직."""

import re


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

    # 대형폐기물 수수료는 종류·규격에 따라 달라진다. 특히 '침대'만으로는
    # 돌/일반, 1/2인용, 매트리스 단독 여부를 구분할 수 없어 최고 금액을
    # 단정하기 쉽다. 검색/LLM 전에 필요한 규격을 먼저 확인한다.
    asks_fee = any(keyword in compact for keyword in ("수수료", "비용", "가격", "얼마"))
    mentions_bed = "침대" in compact or "매트리스" in compact
    has_bed_spec = any(keyword in compact for keyword in (
        "돌침대", "일반침대", "매트리스", "라텍스", "1인용", "2인용",
        "싱글", "더블", "퀸", "킹",
    ))
    if asks_fee and mentions_bed and not has_bed_spec:
        return {
            "answer": (
                "침대 수수료는 종류와 규격에 따라 달라요. "
                "돌침대인지 일반침대인지, 1인용인지 2인용인지 알려주세요. "
                "매트리스만 배출하는 경우도 구분해 주세요."
            ),
            "suggested_questions": [
                "일반침대 1인용 수수료 알려줘",
                "일반침대 2인용 수수료 알려줘",
                "매트리스만 배출할 때 수수료 알려줘",
            ],
        }

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
    """직전 사용자 발화를 현재 질문과 결합해 후속 질문의 검색 문맥을 유지한다."""
    recent_user_messages = [
        (message.get("content") or "").strip()
        for message in (history or [])[-4:]
        if message.get("role") == "user" and (message.get("content") or "").strip()
    ]
    return " ".join(recent_user_messages[-2:] + [user_message.strip()]).strip()
