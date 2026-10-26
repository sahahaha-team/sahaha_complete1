"""Query normalization and substantive topics, independent of models and DB."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache
from chatbot.question_intent import opening_hours_subject, location_subject
from chatbot.vaccination import is_vaccination_query, vaccine_kind

WEAK_WORDS = set("알려 알려줘 알려주세요 뭐야 뭐예요 어떻게 어떻게해 해줘 있어 없어 하고 싶어 인가요 인지 대해 관련 안내 정보 사하 사하구 사하구청 부산 부산광역시 얼마야 얼마 무엇 어디 언제 누구 방법 신고 신청 접수 처리 문의 담당 부서 담당자 인근 근처 주변 주민 민원 사항 내용 업무 가능 필요 경우 절차 준비 최신 현재 지금 오늘 올해 지원 발급 전화 번호 연락처 알려주 자세히 자세한 확인 좀 설명 질문 검색".split())
# Request formats are checked when selecting the actual source section. Their
# absence from a heading must not erase a matching service such as 신규 여권.
WEAK_WORDS.update({"준비물", "준비", "서류", "구비서류", "구비", "성인", "어른", "처음"})
# These describe the request, not the administrative service. They are checked
# against answer fields later, rather than required in every retrieval chunk.
WEAK_WORDS.update("이용 제공 서비스 날짜 기준 각종 제도 도움 때문 어려움 부담 혜택 종류 비용 요금 수수료 금액 기간 시간 운영 대상 조건 자격 부모 특보 절약 주기".split())
WEAK_WORDS.update("법정 한도 부당 처분 도심 의심 행동 발령 사업 건강 검사 상담 비상 시설 문제".split())
WEAK_WORDS.update("어떤 얼마나 몇 며칠 한참 대신 직접 없이 장수 크기 규격 신청자 이용자 참여자 가입자 외래 특실 식비 보호자 지역 가족 아이 아기 어린아이 초등학생 청소년 고등학생 손자 할아버지 월별 생후 개월 주부터 등록증 채무 월세 계약 공짜 포함 이해 답변 따로 이익".split())
WEAK_WORDS.update({'민원서류','계속'})
WEAK_WORDS.update({'엄마','아빠','어머니','아버지','공식','부탁'})
WEAK_WORDS.add('순서')
WEAK_WORDS.update({'기한','퍼센트','비율','연락','요청','진행'})
WEAK_WORDS.update({'의미','방문','대표','대표전화','전화번호'})
WEAK_WORDS.update({'기부금액', '이내'})  # Amount/bound fields, not separate benefits.
WEAK_WORDS.add('출력')  # Output action; the requested document remains the topic.
WEAK_WORDS.update({'도로명주소', '도로명'})  # Address field; parcel-address requests stay distinct.
AREA_PATTERN = re.compile(r"부산(?:광역시)?|사하구(?:청)?|(?:괴정|당리|하단|신평|장림|다대|구평|감천)(?:[1-4])?동|인근|근처|주변")
WORDING_ALIASES = {"보건증": "건강진단결과서", "불법건축물": "위반건축물", "불법주차": "불법주정차", "출산장려금": "출산지원금", "인공지능": "ai", "독감": "인플루엔자", "무료": "무상", "온라인": "인터넷", "도시철도": "지하철", "중개수수료": "중개보수", "빌릴": "대여", "빌리": "대여", "감면": "감경"}
# Keep names intact when morphology splits a service into generic nouns. These
# are vocabulary, not answers or question-to-URL exceptions.
SERVICE_NAMES = ("전입신고", "주민등록등본", "주민등록초본", "정부24", "전자민원",
    "정보공개청구", "건강진단결과서", "물리치료", "방문건강", "건강생활지원센터",
    "국가암검진", "조상땅", "탄소포인트", "탄소중립포인트", "소아암", "암환자",
    "대형폐기물", "무인민원발급", "인플루엔자", "폐렴구균", "작은도서관",
    "장애인연금", "장애수당", "장애아동수당", "아이돌봄", "주민세", "구직", "구인",
    "임산부등록", "영양플러스", "고위험임산부", "영유아건강검진", "대사증후군",
    "심뇌혈관질환", "고향사랑기부", "민간임대주택", "중개보수", "디지털", "컴퓨터",
    "민방위", "지진", "옥외대피", "치매", "결핵", "오존경보", "멧돼지", "자전거",
    "공공근로", "기초생활보장", "법정감염병", "건강검진", "검사비용", "행정정보공동이용", "냉장고", "세탁기", "출산축하", "긴급복지", "정신건강")
# Administrative vocabulary, not question/answer pairs. The answer's specific
# field, audience and region are validated against source sections separately.
SERVICE_NAMES += ('여권','민원실','희망도서','통합예약','임산부','영유아','미숙아',
    '고위험임산부','산모신생아','가족사랑카드','다자녀','첫만남이용권',
    '생계급여','의료급여','기초생활','1인가구','응시료','자격증',
    '마을세무사','납세자보호관','재산세','자동차세','취득세','공시지가',
    '대형폐가전','소형폐가전','구민안전보험','공영주차장','다대포해수욕장',
    '축구장','테니스장','해양경찰정비창','사전컨설팅감사','행정서비스헌장',
    '마을기업','지역공동체일자리','치아홈메우기','정보공개청구','비상급수')
WORDING_ALIASES.update({'무인발급기':'무인민원발급', '무인민원발급기':'무인민원발급',
    '암치료비':'암환자', '암 치료비':'암환자', '암의료비':'암환자',
    '임산부 등록':'임산부등록', '조상 땅':'조상땅', '행정서비스 헌장':'행정서비스헌장',
    '컨설팅감사':'컨설팅감사', '치아 홈메우기':'치아홈메우기'})
SERVICE_NAMES += ('다대포체육시설','가정위탁','1기업1세대','지방세','간판')
SERVICE_NAMES += ('b형간염','a형간염','수수료면제')
SERVICE_NAMES += ('쓰레기',)
SERVICE_NAMES += ('주민등록증', '소방', '자전거도로')
SERVICE_NAMES += ('인감증명', '본인서명사실확인서')
SERVICE_NAMES += ('정보공개', '금연')
SERVICE_NAMES += ('정보화교육',)
SERVICE_NAMES += ('마을건강센터',)
WORDING_ALIASES.update({'인감증명서':'인감증명'})
WORDING_ALIASES.update({'껍데기':'껍질'})
WORDING_ALIASES.update({'aids':'에이즈','갱신':'연장'})
WORDING_ALIASES.update({'자전거길':'자전거도로'})
WORDING_ALIASES.update({'시험비':'응시료','시험료':'응시료'})
WORDING_ALIASES.update({'대피소':'대피시설'})
WORDING_ALIASES.update({'희망책':'희망도서'})
WORDING_ALIASES.update({'다대포 축구장':'다대포체육시설 축구장',
    '다대포축구장':'다대포체육시설 축구장','공시 지가':'공시지가',
    '부동산 등기부등본':'등기사항증명서','부동산등기부등본':'등기사항증명서'})

_SERVICE_SPACING = re.compile('|'.join(r'\s*'.join(map(re.escape, name))
    for name in sorted(set(SERVICE_NAMES) | {'보건소', '금연클리닉'}, key=lambda n: (-len(n), n))
    if len(name) >= 3))


def strip_general_question_tail(query: str) -> str:
    """Neutral state questions do not themselves request an application method.

    Explicit actions/fields before the ending remain: 발급 절차, 신청 방법,
    진료시간, 비용 and 조건 are still checked independently.
    """
    return re.sub(r'\s*어떻게\s*(?:돼(?:요)?|되(?:나요|어요|죠|니)|됩니까|되는데|되는지)\s*[?？.!]*\s*$', '', query or '')


@lru_cache(maxsize=1024)
def normalize_query(query: str) -> str:
    """Normalize surface wording without inventing a service or condition."""
    text = strip_general_question_tail(unicodedata.normalize('NFC', query or ""))
    # Closed vocabulary corrections only. Do not fuzzy-match arbitrary names,
    # numbers, districts or eligibility conditions.
    for typo, name in (('주민등룍증', '주민등록증'), ('대형페기물', '대형폐기물')):
        text = text.replace(typo, name)
    text = re.sub(r'재\s+발급', '재발급', text)
    text = re.sub(r'다시\s*발급', '재발급', text)
    text = re.sub(r'몇\s*일', '며칠', text)
    text = re.sub(r'희망\s*책', '희망도서', text)
    text = re.sub(r'돈\s*(?:을\s*)?안\s*내고', '무료로', text)
    # Known service words may be spaced between syllables. Keep the surrounding
    # sentence, including negation and applicant facts, intact.
    text = _SERVICE_SPACING.sub(lambda match: re.sub(r'\s+', '', match.group()), text)
    # Colloquial questions insert words such as '어떻게' between the typo and
    # '신고', and often omit spaces. News and film festivals are not incidents.
    text = re.sub(r"(?<!영)화제(?!가\s*된|의|로\s*떠|성)(?=[^.!?\n]{0,30}(?:신고|발생|났|나고|진압|대피|119))",
                  "화재", text)
    text = re.sub(r'화재\s*예방\s*교육', '소방 안전교육', text)
    # Bound the abbreviation so 시민증/외국인등록증 are not transformed.
    return re.sub(r'(?<![가-힣])민증(?=\s|[?？.!]|$|은|는|을|이|의|발급|재발급|분실)', '주민등록증', text)


@lru_cache(maxsize=512)
def interpret_query(query: str) -> str:
    """Use the affirmative request in an explicit correction, for routing only.

    Raw input is still checked for privacy and retained as the user's message.
    This is deliberately separate from compact(), which also reads evidence.
    """
    text = normalize_query(query)
    # Remove only an explicitly rejected lifecycle, never a rejected service,
    # age, place, or a condition such as '신분증 없이'. A following affirmative
    # request is required, so '재발급이 아니에요' is not silently reinterpreted.
    pattern = r'(?:신규\s*(?:발급)?|처음\s*발급|재발급|발급)\s*(?:(?:이|가)\s*아니라|말고)\s*(?=.{1,80}(?:발급|분실|신고|수령))'
    return re.sub(pattern, '', text)


@lru_cache(maxsize=8192)
def compact(value: str) -> str:
    value = re.sub(r"[^가-힣a-z0-9]", "", normalize_query(value).lower())
    for alias, target in WORDING_ALIASES.items():
        value = value.replace(alias, target)
    value = value.replace("주민등록표등본", "주민등록등본").replace("주민등록등초본", "주민등록등본주민등록초본")
    value = re.sub(r'임산부.{0,8}등록', '임산부등록', value)
    return re.sub(r'[^가-힣a-z0-9]', '', value)


def service_term_present(term: str, text: str) -> bool:
    if term in ('소방','지진','구인','구직'):
        # Removing spaces from "보건소 방문" creates the unrelated string
        # "소방". Accept a real fire-service word, including 사하소방서.
        return bool(re.search(r'(?<![가-힣])(?:사하구(?:청)?|사하|부산(?:광역시)?)?'+re.escape(term), normalize_query(text)))
    return term in compact(text)


def service_names(query: str) -> set[str]:
    """Preserve the specific administrative topic, not just its broad family."""
    text = compact(query)
    names = {name for name in SERVICE_NAMES if name in text and service_term_present(name,query)}
    if re.search(r'자전거(?:전용)?도로', text):
        names.add('자전거도로')
    return {name for name in names if not any(name != other and name in other for other in names)}


def subject_query(query: str) -> str:
    text = location_subject(opening_hours_subject(strip_general_question_tail(normalize_query(query))))
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
    subject = subject_query(query)
    text = compact(subject)
    from chatbot.official_faq import required_faq_ids
    if required_faq_ids(query) == {1, 2}:
        return {'구청'}  # Address plus main phone still names one institution.
    if re.search(r'면제|장애인등록증.*(?:공짜|무료)', query) and re.search(r'수수료|발급비|발급|민원서류',query):
        return {'수수료면제'}
    names = service_names(subject_query(query))
    if re.search(r'임산부.{0,12}등록',compact(query)):
        names.add('임산부등록')
    if '다대포체육시설' in names:
        names.discard('축구장')
    names = {name for name in names if not any(name != other and name in other for other in names)}
    if re.search(r'이미.*서류|기관.*가지고.*서류|서류.*다시.*제출|중복.*제출|공무원.*서류.*확인.*종이', compact(query)):
        names.add('행정정보공동이용')
        return {'행정정보공동이용'}
    topics = substantive_keywords(words)
    # Kiwi can split '방문수거는' into 방문/수/거 while preserving 수거
    # before another noun. Preserve the explicitly written request noun;
    # do not promote arbitrary character fragments to service names.
    if re.search(r'(?<![가-힣])수거(?=\s|는|은|를|가|이|해|하|[?？]|$)|(?:방문|무상)\s*수거', subject):
        topics.add('수거')
    if re.search(r'가구.*(?:버리|배출)|소파.*(?:버리|배출|수수료|비용)',query):
        return {'대형폐기물'}
    if '금연' in query and '클리닉' in query:
        return {'금연','클리닉'}
    if re.search(r'생활비.*지원|지원.*생활비',query) and re.search(r'실직|갑자기.*소득',query):
        return {'긴급복지'}
    if re.search(r'혼자\s*사|1인\s*가구',query) and re.search(r'청소|반찬',query):
        return {'1인가구'}
    if '자격증' in names and re.search(r'시험비|시험료|응시|지원',query):
        return {'응시료'}
    if re.search(r'(?:아기|영유아|생후).*건강검진|영유아.*구강검진',text):
        return {'영유아건강검진'}
    if '폐암' in query and '검진' in query:
        return {'국가암검진'}
    if '정신건강' in names and '우울감' in topics:
        topics.discard('우울감')  # Symptom wording must not reject the mental-health service.
    if not topics - {'보건소'} and re.search(r'검사.{0,3}(?:비용|수수료|요금)', text):
        names.add('검사비용')  # The fee table remains a real service subject.
    if '민방위' in names and '대피' in text and '급수' in text:
        topics -= {'대피','급수'}  # A combined facility inquiry can first narrow the location.
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
        topics -= {'주소','위치','지도','노선','노선도','현황도','링크','페이지'}
        if len(names) > 1:
            names.discard('검사비용')
        topics = {word for word in topics if not any(word in name for name in names)} | names
        topics -= {'홈페이지', '웹사이트', '사이트'}
        if names.intersection({'디지털','컴퓨터'}):
            topics.discard('교육')
            topics.discard('컴퓨터')
            topics.add('디지털')
        if '건강검진' in names:
            topics.discard('국가')
        if '주민세' in names:
            topics -= {'인터넷', '종업원', '사업소'}
        if '행정정보공동이용' in names:
            topics -= {'행정', '기관', '서류', '제출'}
        if names.intersection({'결핵', '치매', '대사증후군', '영유아건강검진', '심뇌혈관질환'}):
            topics -= {'검사', '건강', '상담', '관리', '예방', '질환', '혈압', '당뇨', '뇌혈관'}
        # Conditions such as youth, photos, reservation or a requested month
        # describe answer fields. Requiring them in every chunk prevented the
        # right service from reaching the source reader at all.
        strong = names - {'구직','구인','디지털','컴퓨터','자전거','냉장고','세탁기'}
        if strong:
            topics = strong | (topics & {'신규','도로','일반'} if '쓰레기' in strong else topics & {'신규','도로'})
            if '주민등록증' in strong:
                # Its official first-issue guide says 발급신청, while the
                # separate lifecycle guard still rejects 재발급 for 신규.
                topics.discard('신규')
            if '암환자' in strong and re.search(r'치료비|의료비',query):
                topics.add('의료비')
    if "정부24" in names:
        topics.discard("구청")  # '구청에 가지 않고' is not another service.
    elif len(topics) > 1:
        topics.discard("구청")
    if "방문건강" in names:
        topics -= {"거동", "불편", "관리"}
    if len(topics) > 1:
        topics.discard('보건소')
    if '출산축하' in names:
        topics -= {'아이', '이상'}
    if '긴급복지' in names:
        topics.discard('생계')
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
