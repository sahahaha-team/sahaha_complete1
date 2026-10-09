"""Welcome categories ask for a service before retrieving factual guidance."""
import re


MENUS = {
    "구청안내해줘": (
        "구청의 **위치·대표전화·민원 담당 부서** 중 무엇이 궁금하신가요?",
        [("사하구청 위치 알려줘", ("위치", "주소")),
         ("사하구청 대표전화 알려줘", ("대표전화", "전화", "연락처")),
         ("민원여권과 전화번호 알려줘", ("민원", "민원담당부서"))]),
    "복지서비스안내해줘": (
        "**누구를 위한 지원**을 찾으시나요? 지원 대상을 선택해 주세요.",
        [("어르신 복지 지원 알려줘", ("어르신", "노인")),
         ("아동·보육 지원 알려줘", ("아동", "보육", "아이")),
         ("장애인 복지 지원 알려줘", ("장애인",))]),
    "민원안내해줘": (
        "**등본·여권·무인민원발급기** 중 어떤 안내가 필요하신가요?",
        [("주민등록등본 발급 방법 알려줘", ("등본", "주민등록등본")),
         ("여권 준비 서류 알려줘", ("여권",)),
         ("무인민원발급기 위치 알려줘", ("무인민원발급기", "발급기"))]),
    "생활환경안내해줘": (
        "**생활쓰레기·재활용품·대형폐기물** 중 무엇을 버리시나요?",
        [("쓰레기 배출 방법 알려줘", ("생활쓰레기", "쓰레기")),
         ("재활용품 분리배출 방법 알려줘", ("재활용", "재활용품")),
         ("대형폐기물 배출 방법 알려줘", ("대형폐기물", "대형"))]),
}


def navigation_key(message: str) -> str:
    return re.sub(r"[\s?!.,]", "", message or "")


def navigation_clarification(message: str) -> dict | None:
    menu = MENUS.get(navigation_key(message))
    if menu is None:
        return None
    answer, choices = menu
    return {"answer": answer, "suggested_questions": [question for question, _ in choices],
            "reply_terms": [alias for _, aliases in choices for alias in aliases]}


def navigation_reply(message: str, previous: str) -> str | None:
    menu = MENUS.get(navigation_key(previous))
    if menu:
        for question, aliases in menu[1]:
            if navigation_key(message) in aliases:
                return question
    return None


def is_council_location_query(message: str) -> bool:
    """Only the main council building; exclude named departments/second offices."""
    return bool(re.fullmatch(
        r"(?:부산(?:광역시)?)?(?:사하구청|구청)(?:의|은|는)?"
        r"(?:위치|주소|찾아가는길|오시는길|어디야|어디에있어|어디에있나요|어디인가요|어디예요)"
        r"(?:(?:와|과|및)?(?:연락처|대표전화|전화번호))?"
        r"(?:알려줘|알려주세요|안내해줘)?", navigation_key(message)))
