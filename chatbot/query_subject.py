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
# These describe the request, not the administrative service. They are checked
# against answer fields later, rather than required in every retrieval chunk.
WEAK_WORDS.update("이용 제공 서비스 날짜 기준 각종 제도 도움 때문 어려움 부담 혜택 종류 비용 요금 수수료 금액 기간 시간 운영 대상 조건 자격 부모 특보 절약 주기".split())
AREA_PATTERN = re.compile(r"부산(?:광역시)?|사하구(?:청)?|(?:괴정|당리|하단|신평|장림|다대|구평|감천)(?:[1-4])?동|인근|근처|주변")
WORDING_ALIASES = {"보건증": "건강진단결과서", "불법건축물": "위반건축물", "불법주차": "불법주정차", "출산장려금": "출산지원금", "인공지능": "ai", "독감": "인플루엔자", "무료": "무상", "온라인": "인터넷", "도시철도": "지하철"}
# Keep names intact when morphology splits a service into generic nouns. These
# are vocabulary, not answers or question-to-URL exceptions.
SERVICE_NAMES = ("전입신고", "주민등록등본", "주민등록초본", "정부24", "전자민원",
    "정보공개청구", "건강진단결과서", "물리치료", "방문건강", "건강생활지원센터",
    "국가암검진", "조상땅", "탄소포인트", "탄소중립포인트", "소아암", "암환자",
    "대형폐기물", "무인민원발급", "인플루엔자", "폐렴구균", "작은도서관")


def normalize_query(query: str) -> str:
    """Correct 화제 only in an explicit fire incident/reporting context."""
    text = query or ""
    # Colloquial questions insert words such as '어떻게' between the typo and
    # '신고', and often omit spaces. News and film festivals are not incidents.
    return re.sub(r"(?<!영)화제(?!가\s*된|의|로\s*떠|성)(?=[^.!?\n]{0,30}(?:신고|발생|났|나고|진압|대피|119))",
                  "화재", text)


def compact(value: str) -> str:
    value = re.sub(r"[^가-힣a-z0-9]", "", normalize_query(value).lower())
    for alias, target in WORDING_ALIASES.items():
        value = value.replace(alias, target)
    value = value.replace("주민등록표등본", "주민등록등본").replace("주민등록등초본", "주민등록등본주민등록초본")
    return value


def subject_query(query: str) -> str:
    text = location_subject(opening_hours_subject(normalize_query(query)))
    # 구청 is a facility in directions questions, not just a region name.
    text = AREA_PATTERN.sub(" ", text.replace("사하구청", "구청"))
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


def query_keywords(query: str, words: Iterable[str]) -> set[str]:
    text = compact(subject_query(query))
    names = {name for name in SERVICE_NAMES if name in text}
    topics = substantive_keywords(words)
    from chatbot.answer_goal import answer_goal
    if answer_goal(query) == 'reference':
        # Requested display formats are not extra services that every body
        # must mention. Keep them for map-only queries without a real subject.
        navigation = {'지도', '현황도', '링크', '사이트', '페이지', '조회', '다운로드'}
        if topics - navigation:
            topics -= navigation
    if re.search(r'일반\s*(?:주민|구민|시민)', query):
        topics.discard('일반')  # Audience condition, distinct from 일반쓰레기.
    if names:
        topics = {word for word in topics if not any(word in name for name in names)} | names
        topics -= {'홈페이지', '웹사이트', '사이트'}
    if "정부24" in names:
        topics.discard("구청")  # '구청에 가지 않고' is not another service.
    elif len(topics) > 1:
        topics.discard("구청")
    if "방문건강" in names:
        topics -= {"거동", "불편", "관리"}
    if "조상" in topics and "땅" in query:
        topics.discard("조상")
        topics.add("조상땅")
    if "구청" in text and not topics:
        topics.add("구청")
    if ("민원" in text and "인터넷" in text):
        topics.discard("인터넷")
        topics.add("전자민원")
    return substantive_keywords(topics)


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
    return query_keywords(query, words)
