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
                "배출할 품목의 정확한 규격을 한 가지만 알려주세요. "
                "예: 일반침대 2인용, 돌침대 1인용, 매트리스 단독"
            ),
            "suggested_questions": [
                "일반침대 1인용 수수료 알려줘",
                "일반침대 2인용 수수료 알려줘",
                "매트리스만 배출할 때 수수료 알려줘",
            ],
        }

    # 멀티턴은 답이 실제 조건에 따라 달라지는 경우로 제한한다. 복지·세금·민원·
    # 쓰레기·예약·보건소 같은 분야형 질문은 먼저 공식 자료의 개요를 답한다.
    # 다만 업무명 없이 담당자/전화번호만 요구하면 후보를 고를 수 없으므로
    # 그때만 한 가지 업무를 확인한다.
    contact_terms = ("담당자", "담당부서", "연락처", "전화번호", "문의")
    asks_office_basics = (
        any(term in compact for term in ("사하구청", "구청"))
        and any(term in compact for term in ("위치", "주소", "대표", "오시는길"))
    )
    if (
        any(term in compact for term in contact_terms)
        and len(compact) <= 13
        and not asks_office_basics
    ):
        return {
            "answer": "어떤 민원이나 업무의 담당자를 찾으시는지 알려주세요.",
            "suggested_questions": [
                "대형폐기물 담당자 전화번호 알려줘",
                "불법주정차 담당 부서 알려줘",
                "여권 업무 문의처 알려줘",
            ],
        }

    return None

    # 생활폐기물은 종류와 지역에 따라 배출 방법·요일이 달라질 수 있다.
    waste_terms = ("쓰레기", "폐기물", "배출", "분리수거")
    waste_types = (
        "일반쓰레기", "생활쓰레기", "음식물", "재활용", "대형폐기물",
        "대형쓰레기", "폐가전", "종량제", "유리", "캔", "종이", "비닐", "침대", "가구",
    )
    asks_waste = any(term in compact for term in waste_terms)
    has_waste_type = any(term in compact for term in waste_types)
    if asks_waste and not has_waste_type and len(compact) <= 16:
        return {
            "answer": "어떤 종류의 쓰레기인지 알려주세요. 종류에 따라 배출 방법과 수거 방식이 달라요.",
            "suggested_questions": [
                "일반 생활쓰레기 배출 방법 알려줘",
                "음식물쓰레기 배출 방법 알려줘",
                "대형폐기물 배출 방법 알려줘",
            ],
        }

    # 예약은 시설·프로그램이 결정되지 않으면 서로 다른 예약 페이지가 섞인다.
    reservation_terms = ("예약", "강좌", "교육", "체험")
    reservation_targets = (
        "도서관", "소방", "평생학습", "정보화", "체육", "문화회관",
        "프로그램", "강좌명", "어린이", "성인", "청소년",
    )
    asks_reservation = any(term in compact for term in reservation_terms)
    has_reservation_target = any(term in compact for term in reservation_targets)
    if asks_reservation and not has_reservation_target and len(compact) <= 16:
        return {
            "answer": "어느 시설이나 프로그램을 예약하려는지 알려주세요.",
            "suggested_questions": [
                "도서관 교육 프로그램을 예약하고 싶어요",
                "소방안전체험 예약 방법 알려줘",
                "평생학습관 강좌 신청 방법 알려줘",
            ],
        }

    # 보건소 업무는 진료·검사·접종별 시간과 대상이 달라 한 단어 질문에
    # 임의의 업무를 선택하지 않는다.
    health_terms = ("보건소", "예방접종", "검사", "검진", "진료")
    health_targets = (
        "성인", "어린이", "영유아", "결핵", "보건증", "건강진단결과서",
        "물리치료", "암검진", "임산부", "금연", "대사증후군", "치매",
        "몇시", "시간", "운영", "문여",
    )
    asks_health = any(term in compact for term in health_terms)
    has_health_target = any(term in compact for term in health_targets)
    if asks_health and not has_health_target and len(compact) <= 14:
        return {
            "answer": "보건소에서 어떤 업무를 이용하려는지 알려주세요.",
            "suggested_questions": [
                "보건소 진료시간과 위치 알려줘",
                "성인 예방접종 시간 알려줘",
                "보건증 발급 비용과 기간 알려줘",
            ],
        }

    # 실제 업무명 없이 담당자/전화번호만 요구하면 직원검색의 모든 행이 후보가 된다.
    contact_terms = ("담당자", "담당부서", "연락처", "전화번호", "문의")
    asks_office_basics = (
        any(term in compact for term in ("사하구청", "구청"))
        and any(term in compact for term in ("위치", "주소", "대표", "오시는길"))
    )
    if (
        any(term in compact for term in contact_terms)
        and len(compact) <= 13
        and not asks_office_basics
    ):
        return {
            "answer": "어떤 민원이나 업무의 담당자를 찾으시는지 알려주세요.",
            "suggested_questions": [
                "대형폐기물 담당자 전화번호 알려줘",
                "불법주정차 담당 부서 알려줘",
                "여권 업무 문의처 알려줘",
            ],
        }

    # 아래 질문들은 검색 범위가 넓을 때만 조건 하나를 확인한다. 대상이나 종류가
    # 이미 들어 있으면 이 분기를 타지 않고 곧바로 공식 자료를 검색한다.
    welfare_terms = ("복지", "지원", "혜택", "수당")
    welfare_targets = (
        "어르신", "노인", "장애", "아동", "청소년", "한부모", "임산부",
        "영유아", "기초생활", "차상위", "청년", "다자녀", "보훈",
    )
    if (
        any(term in compact for term in welfare_terms)
        and not any(term in compact for term in welfare_targets)
        and len(compact) <= 14
    ):
        return {
            "answer": "어느 대상의 복지·지원인지 한 가지만 알려주세요.",
            "suggested_questions": [
                "어르신 복지 지원 알려줘",
                "장애인 복지 지원 알려줘",
                "한부모가족 지원 알려줘",
            ],
        }

    tax_terms = ("세금", "지방세", "세무")
    tax_targets = ("주민세", "재산세", "자동차세", "취득세", "등록면허세", "납부", "환급")
    if (
        any(term in compact for term in tax_terms)
        and not any(term in compact for term in tax_targets)
        and len(compact) <= 12
    ):
        return {
            "answer": "어떤 세금에 관한 안내가 필요한지 한 가지만 알려주세요.",
            "suggested_questions": [
                "주민세 신고 방법 알려줘",
                "재산세 납부 방법 알려줘",
                "자동차세 안내해줘",
            ],
        }

    civil_terms = ("민원", "증명서", "서류", "발급")
    civil_targets = (
        "등본", "초본", "인감", "여권", "가족관계", "전입", "출생", "사망",
        "건축", "토지", "무인민원", "온라인", "인터넷",
    )
    if (
        any(term in compact for term in civil_terms)
        and not any(term in compact for term in civil_targets)
        and len(compact) <= 12
    ):
        return {
            "answer": "어떤 민원이나 증명서인지 한 가지만 알려주세요.",
            "suggested_questions": [
                "주민등록등본 발급 방법 알려줘",
                "여권 신청 방법 알려줘",
                "가족관계증명서 발급 방법 알려줘",
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
    """짧은 후속 질문일 때만 직전 사용자 발화를 검색 문맥에 결합한다."""
    current = (user_message or "").strip()
    compact = re.sub(r"[\s?!.,]", "", current)
    words = current.replace("?", " ").replace("!", " ").split()
    follow_up_markers = (
        "그거", "그것", "그건", "그럼", "그러면", "아까", "위내용", "앞에서",
        "이어서", "그중", "그중에", "그방법", "그곳", "해당",
    )
    is_short_follow_up = len(words) <= 2 and len(compact) <= 12
    explicitly_contextual = any(marker in compact for marker in follow_up_markers)

    # 새 업무명이 충분히 들어간 독립 질문에 과거 주제를 섞으면, 이전 답변의
    # FAQ가 현재 질문보다 높게 랭크되어 오출처가 생긴다.
    if not (is_short_follow_up or explicitly_contextual):
        return current

    recent_user_messages = [
        (message.get("content") or "").strip()
        for message in (history or [])[-4:]
        if message.get("role") == "user" and (message.get("content") or "").strip()
    ]
    return " ".join(recent_user_messages[-1:] + [current]).strip()
