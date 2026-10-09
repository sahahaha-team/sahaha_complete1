"""Query normalization and substantive topics, independent of models and DB."""
from __future__ import annotations

import re
from collections.abc import Iterable
from chatbot.question_intent import opening_hours_subject, location_subject
from chatbot.vaccination import is_vaccination_query, vaccine_kind

WEAK_WORDS = set("알려 알려줘 알려주세요 뭐야 뭐예요 어떻게 어떻게해 해줘 있어 없어 하고 싶어 인가요 인지 대해 관련 안내 정보 사하 사하구 사하구청 부산 부산광역시 얼마야 얼마 무엇 어디 언제 누구 방법 신고 신청 접수 처리 문의 담당 부서 담당자 인근 근처 주변 주민 민원 사항 내용 업무 가능 필요 경우 절차 준비 최신 현재 지금 오늘 올해 지원 발급 전화 번호 연락처 알려주 자세히 자세한 확인 좀 설명 질문 검색".split())
# Request formats are checked when selecting the actual source section. Their
# absence from a heading must not erase a matching service such as 신규 여권.
WEAK_WORDS.update({"준비물", "준비", "서류", "구비서류", "구비", "성인", "어른", "처음"})
WEAK_WORDS.update({"기준", "날짜", "조건", "자격", "대상", "수급", "어떤"})
WEAK_WORDS.update({"서비스", "사업", "종류", "이용", "사람", "가정", "내용", "가구", "살", "이상", "이하", "자주", "주기", "인터넷", "온라인", "곳", "것", "때", "내", "수", "누가", "원", "회", "도움", "어려움", "문제", "전", "후", "비용", "기간", "제도"})
WEAK_WORDS.update({'구청', '위치', '주소', '홈페이지', '차량', '부과', '기관', '제출'})
WEAK_WORDS.update({'혜택', '행동', '도심', '부담', '특보', '발령', '거동', '불편'})
AREA_PATTERN = re.compile(r"부산(?:광역시)?|사하구(?:청)?|(?:괴정|당리|하단|신평|장림|다대|구평|감천)(?:[1-4])?동|인근|근처|주변")
WORDING_ALIASES = {"보건증": "건강진단결과서", "불법건축물": "위반건축물", "불법주차": "불법주정차", "출산장려금": "출산지원금", "인공지능": "ai", "독감": "인플루엔자", '간판': '옥외광고물', '법정한도': '법정상한', '도시철도': '지하철', '국가건강검진': '일반건강검진'}


def normalize_query(query: str) -> str:
    """Normalize unambiguous typos without changing the requested service."""
    text = re.sub(r"어른신", "어르신", query or "")
    return re.sub(r"(?<!영)화제(?=\s*(?:가\s*)?(?:신고|발생|났|나고|진압|대피|현장))", "화재", text)


def disposal_method_kind(query: str) -> str | None:
    """Recognize a basic disposal request, including a narrowed short reply."""
    value = re.sub(r"[\s?!.,]", "", query or "")
    value = re.sub(r"^(?:부산광역시)?사하구(?:청)?(?:에서는|에서|의)?", "", value)
    match = re.fullmatch(
        r"(?:쓰레기배출(?:방법|요령|안내)?(?:알려(?:줘|주세요))?)?"
        r"(?P<kind>일반쓰레기|음식물(?:쓰레기)?|재활용품|재활용|분리수거|분리배출)"
        r"(?:은|는|을|를)?(?:분리배출|분리수거|배출|버리는|어떻게버려)?"
        r"(?:방법|요령|법)?(?:알려(?:줘|주세요))?", value)
    if not match:
        return None
    kind = match['kind']
    return '일반' if kind == '일반쓰레기' else '음식물' if kind.startswith('음식물') else '재활용'


def compact(value: str) -> str:
    value = re.sub(r"[^가-힣a-z0-9]", "", normalize_query(value).lower())
    for alias, target in WORDING_ALIASES.items():
        value = value.replace(alias, target)
    return value


def subject_query(query: str) -> str:
    text = AREA_PATTERN.sub(" ", location_subject(opening_hours_subject(normalize_query(query))))
    # Normalize full wording before morphology splits it: 불법주차 must become
    # 불법주정차, rather than leaving the fragment 주차 unmatched by 주정차.
    for alias, target in WORDING_ALIASES.items():
        text = text.replace(alias, target)
    if vaccine_kind(query) and is_vaccination_query(query):
        # The type, rather than repeated generic vaccine words, must match.
        text = re.sub(r'예방접종|접종|백신|예방주사', ' ', text)
    if '여권' in text and any(word in text for word in ('미성년', '아이', '자녀', '18세 미만')):
        text = text.replace('부모', '친권자')
    return text


def substantive_keywords(words: Iterable[str]) -> set[str]:
    output = set()
    for word in words:
        word = compact(word)
        if len(word) < 2 or word.isdigit() or word in WEAK_WORDS:
            continue
        if AREA_PATTERN.fullmatch(word):
            continue
        output.add(word)
    # '대형폐기물' and '폐기물' are one topic, not two independent signals.
    return {word for word in output if not any(word != longer and word in longer for longer in output)}


def fallback_keywords(query: str) -> set[str]:
    text = subject_query(query)
    text = re.sub(r"알려(?:주세요|줘)?|어떻게(?:해|하나요)?|무엇|뭐야|좀", " ", text)
    words = []
    for word in re.findall(r"[가-힣A-Za-z0-9]+", text):
        word = re.sub(r"(?:으로|에서|에게|은|는|을|를|이|가|의|에|요)$", "", word) if len(word) >= 3 else word
        words.append(word)
    return substantive_keywords(words)
