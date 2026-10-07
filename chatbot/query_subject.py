"""Query normalization and substantive topics, independent of models and DB."""
from __future__ import annotations

import re
from collections.abc import Iterable

WEAK_WORDS = set("알려 알려줘 알려주세요 뭐야 뭐예요 어떻게 어떻게해 해줘 있어 없어 하고 싶어 인가요 인지 대해 관련 안내 정보 사하 사하구 사하구청 부산 부산광역시 얼마야 얼마 무엇 어디 언제 누구 방법 신고 신청 접수 처리 문의 담당 부서 담당자 인근 근처 주변 주민 민원 사항 내용 업무 가능 필요 경우 절차 준비 최신 현재 지금 오늘 올해 지원 발급 전화 번호 연락처 알려주 자세히 자세한 확인 좀 설명 질문 검색".split())
# Request formats are checked when selecting the actual source section. Their
# absence from a heading must not erase a matching service such as 신규 여권.
WEAK_WORDS.update({"준비물", "준비", "서류", "구비서류", "구비", "성인", "어른", "처음"})
AREA_PATTERN = re.compile(r"부산(?:광역시)?|사하구(?:청)?|(?:괴정|당리|하단|신평|장림|다대|구평|감천)(?:[1-4])?동|인근|근처|주변")
WORDING_ALIASES = {"보건증": "건강진단결과서", "불법건축물": "위반건축물", "불법주차": "불법주정차", "출산장려금": "출산지원금", "인공지능": "ai"}


def normalize_query(query: str) -> str:
    """Correct 화제 only in an explicit fire incident/reporting context."""
    return re.sub(r"(?<!영)화제(?=\s*(?:가\s*)?(?:신고|발생|났|나고|진압|대피|현장))", "화재", query or "")


def compact(value: str) -> str:
    value = re.sub(r"[^가-힣a-z0-9]", "", normalize_query(value).lower())
    for alias, target in WORDING_ALIASES.items():
        value = value.replace(alias, target)
    return value


def subject_query(query: str) -> str:
    text = AREA_PATTERN.sub(" ", normalize_query(query))
    # Normalize full wording before morphology splits it: 불법주차 must become
    # 불법주정차, rather than leaving the fragment 주차 unmatched by 주정차.
    for alias, target in WORDING_ALIASES.items():
        text = text.replace(alias, target)
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
