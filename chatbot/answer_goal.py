"""Requested answer fields, kept separate from service-topic evidence."""
from __future__ import annotations

import re
from functools import lru_cache

from chatbot.question_intent import asks_location, asks_opening_hours

GOAL_WORDS = {
    "medical_details": ("처방", "약명", "약품명", "복용량", "용량", "복용법"),
    "conditions": ("조건", "가능", "제외", "한도", "유의", "반드시", "다만", "불가", "제한", "금식", "신청"),
    "specifications": ("사진", "규격", "크기", "가로", "세로", "매", "장", "cm"),
    "reference": ("홈페이지", "페이지", "링크", "현황도", "지도", "조회", "확인", "자세히보기", "다운로드"),
    "method": ("방법", "접수", "예약", "신고", "신청", "이용", "발급", "절차", "제출", "등록", "로그인", "회원가입", "전화", "콜센터", "인터넷", "인증", "표기", "작성", "선택", "입력", "조회"),
    "eligibility": ("대상", "조건", "자격", "해당", "소유", "보유", "이상", "이하"),
    "cost": ("수수료", "요금", "비용", "금액", "원", "무료", "무상", "유료"),
    "documents": ("서류", "준비", "지참", "구비", "신분증", "신청서"),
    "schedule": ("시간", "기간", "일정", "주기", "매년", "매월", "연 ", "월 ", "일", "년"),
    "location": ("장소", "주소", "위치", "방문", "기관"),
    "hours": ("시간", "휴무", "평일", "주말"),
    "services": ("내용", "운영", "진료", "검사", "상담", "제공", "지원", "발급", "접수", "신청", "예약"),
    "definition": ("이란", "말합니다", "제도", "사업", "목적", "의미", "위함"),
    "precautions": ("해야", "마세요", "하십시오", "피하", "자제", "주의", "금지", "대피", "행동", "요령"),
    "necessity": ("공동이용", "제출", "생략", "않", "필요", "확인"),
}


def quantity_unit(query: str) -> str | None:
    """A count limit is distinct from a fee or a processing duration."""
    text = re.sub(r'\s+', '', query)
    if re.search(r'몇권|권수|신청수량|(?:도서|책).*(?:한도|몇권)', text):
        return '권'
    if re.search(r'몇회|횟수|몇번', text):
        return '회'
    return None


@lru_cache(maxsize=512)
def answer_goal(query: str) -> str | None:
    from chatbot.query_subject import interpret_query
    query = interpret_query(query)
    compact_query = query.replace(' ', '')
    if quantity_unit(query):
        return 'schedule'
    if re.search(r'통행규칙|안전수칙', compact_query):
        return 'precautions'
    if re.search(r'복용량|복용법|약품명|약이름|어떤약|처방.*이름|용량|약.*(?:몇알|몇정|먹어야)|하루.*몇(?:알|정)', compact_query):
        return 'medical_details'
    # The requested field wins over an incidental action such as 신청/버리는.
    # Applicant conditions and identity-copy questions are not application steps.
    if re.search(r'신분증|증명서', compact_query) and re.search(r'원본|사본|휴대폰사진|사진이면|사진으로', compact_query):
        return 'conditions'
    if re.search(r'대리|대신', compact_query) and re.search(r'신청|발급|접수', compact_query) and re.search(r'해도|할수|가능|되나|돼', compact_query) and not re.search(r'방법|절차|서류|준비|가져', compact_query):
        return 'conditions'
    if re.search(r'(?:몇|만\d+|\d+)(?:세|살)(?:부터|이상|미만|이하)|몇개월부터|나이|연령', compact_query) and not re.search(r'서류|준비|사진|수수료|요금|비용|처리기간', compact_query):
        return 'eligibility'
    if re.search(r'현금|계좌|통장', compact_query) and re.search(r'지급|들어|받|나오', compact_query):
        return 'conditions'
    if re.search(r'뭐가필요|무엇이필요|뭘챙|무엇을챙|챙길(?:것|거)', compact_query):
        return 'documents'
    if re.search(r'수수료|요금|비용|가격|상한', compact_query) and re.search(r'얼마|상한|최대|한도|그대로', compact_query):
        return 'cost'
    if re.search(r'어느달|몇개월|한번만|생일.*달|신청.*마감', compact_query):
        return 'schedule'
    if re.search(r'신청할수|신청(?:이)?가능|기부할수|지원받을수|해도돼|해도되|전부사주|모두사주', compact_query) and not re.search(r'어떻게|방법|절차|순서|어디|언제|몇|누가|누구|대상|서류|준비', compact_query):
        return 'conditions'
    if re.search(r'보조제|제공품|지원품목', compact_query) and re.search(r'지원|제공|주나|주요', compact_query):
        return 'services'
    if re.search(r'어디로해|어디서해', compact_query) and re.search(r'신청|접수|예약|수거', compact_query):
        return 'method'
    if re.search(r'(?:지도|노선도|현황도|공식페이지|공식사이트).*(?:볼수|보려|보고싶|보여|알려|확인|조회)|(?:볼수|확인|조회).*(?:지도|노선도|현황도|공식페이지|공식사이트)', compact_query):
        return 'reference'
    if re.search(r'예약.*(?:해야|필수|먼저)|(?:먼저|사전).*예약', compact_query):
        return 'conditions'
    if (re.search(r'예약.*(?:없이|안하고|않고|안해도|안하)',compact_query)
            and not re.search(r'방법|절차|어떻게',compact_query)):
        return 'conditions'
    if re.search(r'서류.*(?:제출|내).*(?:생략|안내도)|기관.*서류.*확인', compact_query):
        return 'necessity'
    if re.search(r'돈이?들|수강료|재료비|주차장마다.*(?:같|똑같)', compact_query):
        return 'cost'
    if re.search(r'나이.*(?:같|차이)|(?:같|차이).*나이', compact_query):
        return 'eligibility'
    if re.search(r'소득.*재산|재산.*소득', compact_query) and re.search(r'수급|선정|대상', compact_query):
        return 'eligibility'
    if re.search(r'한참뒤|출산.*(?:지나|지난|뒤)',compact_query):
        return 'schedule'
    if re.search(r'사업자등록.*(?:있|없)|매출.*없',compact_query) and not re.search(r'어떻게|방법|신청서|서류',compact_query):
        return 'eligibility'
    if re.search(r'(?:금액|소득기준|과태료).*(?:같|똑같)|(?:같|똑같).*(?:금액|소득기준|과태료)',compact_query):
        return 'eligibility' if '소득' in compact_query else 'cost'
    if re.search(r'거래금액.*(?:정하|계산)|계산할때|환산',compact_query):
        return 'method'
    if re.search(r'갱신|연장해야|계속쓸|표시기간',compact_query):
        return 'schedule'
    if re.search(r'까지만|연간한도|기부한도|돈을내|돈내야',compact_query):
        return 'cost'
    if re.search(r'어느동|어느지역',compact_query):
        return 'location'
    if re.search(r'어떤기업|뭔지|어떤제도|어떤사업',compact_query):
        return 'definition'
    if re.search(r'어떤일|무슨일|하는일|어떤업무|무슨업무',compact_query):
        return 'services'
    if '신분증' in compact_query and re.search(r'있으면|필요|청소년|만으로|만있',compact_query):
        return 'documents'
    if re.search(r'아무때|낮에.*내놓|배출시간|예약없이|예약.*필요|또맞아야|식수로',compact_query):
        return 'schedule' if re.search(r'아무때|내놓|배출시간',compact_query) else 'conditions'
    if re.search(r'사진|몇장|크기|규격|가로|세로',compact_query):
        if not re.search(r'구비|준비물|준비서류',compact_query):
            return 'specifications'
    if re.search(r'이미.*서류|기관.*가지고.*서류|서류.*다시.*제출|중복.*제출', compact_query):
        return 'necessity'
    if re.search(r'종이로.*또.*내|종이.*다시.*내', compact_query):
        return 'necessity'
    if re.search(r'가입.*(?:해야|필요)|따로가입|자동.*가입|가입되나요', compact_query):
        return 'necessity'
    if re.search(r'당일.*(?:나와|발급|받)|다음날.*(?:받|발급)',compact_query):
        return 'schedule'
    if re.search(r'무조건|포함|똑같|같나요|같아요|하이픈|띄어쓰기|밥먹고|금식|당일나와|장부작성|공동인증서만|한참뒤|식비|특실|외래재활|모든.*(?:무료|공짜|끝)|그대로받|현금.*통장|어디에쓰',compact_query):
        return 'conditions'
    if re.search(r'종류|어떤급여|급여에는무엇', compact_query):
        return 'services'
    if re.search(r'준비물|구비서류|필요한서류|서류.*(?:무엇|뭐|필요)', compact_query):
        return 'documents'
    if re.search(r'무엇인가|무엇이고|뭐야|뭐예요|이란|어떤제도|어떤사업', compact_query):
        return 'definition'
    if re.search(r'마주치|행동|주의사항|폭염.*주의|예방수칙', compact_query):
        return 'precautions'
    if re.search(r'버려야|배출해야|물기를|버리는', compact_query):
        return 'method'
    if re.search(r'감경|할인|자진납부|깎', compact_query):
        return 'cost'
    if re.search(r'무료|무상', query) and re.search(r'수거|대여|대출', query) and not re.search(r'방법|어떻게|신청',query):
        return 'cost'
    if re.search(r'발급\s*받을\s*수|가지\s*않고.*발급',query) and not re.search(r'어떻게|방법|절차',query):
        return 'services'
    if (any(word in compact_query for word in ("어떤서비스", "어떤진료", "무슨서비스", "어떤지원"))
            or re.search(r'(?:어떤|무슨).{0,20}(?:서비스|진료)|서비스(?:에는|는|가)?(?:무엇|뭐|어떤|종류)', compact_query)):
        return "services"
    link_requested = "링크" in query and not re.search(r'링크\s*(?:는|가|도)?\s*(?:말고|필요\s*없|제외|빼고)', query)
    if (link_requested or ("어디" in query and any(word in query for word in (
            "확인", "찾아볼", "찾아보", "조회", "볼 수", "볼수", "보나요", "현황도", "지도", "사이트")))):
        return "reference"
    if re.search(r'인터넷|온라인|홈페이지', query) and re.search(r'찾아볼|조회할', query):
        return 'reference'
    if asks_opening_hours(query):
        return "hours"
    if re.search(r'점심|저녁|낮에|밤에|야간',compact_query) and re.search(r'민원|여권|접수|신청|방문',compact_query):
        return 'hours'
    if re.search(r'어디(?:서|로).{0,6}(?:신청|접수|제출)',compact_query):
        return 'method'
    if asks_location(query):
        return "location"
    if re.search(r'대피소|대피시설|급수시설',query) and re.search(r'찾고|근처|인근',query):
        return 'location'
    if any(word in query for word in ("서류", "준비물", "구비", "준비해야")) and not any(word in query for word in ("발급", "신청", "어떻게")):
        return "documents"
    if any(word in query for word in ("준비물", "구비", "준비해야", "필요한 서류")) or (
            re.search(r'가져가|가져갈',query) and not re.search(r'수거|가져가.*서비스|와서.*가져가',query)):
        return "documents"
    if re.search(r'통행료|입장료|사용료', query) and re.search(r'무료|무상|면제|얼마|금액|할인|감면', query):
        return 'cost'
    if (any(word in query for word in ("비용", "발급비", "수수료", "요금", "금액", "얼마나 지원", "얼마나 주")) or re.search(r'얼마(?!나)',query)) and not any(word in query for word in ("자주", "무료", "무상", "부담")):
        return "cost"
    if any(word in query for word in ("대상", "조건", "자격", "누가", "누구", "몇 살", "몇살")):
        return "eligibility"
    if any(word in query for word in ("언제", "기간", "며칠", "주기", "자주", "날짜", "몇 번", "몇 월", "몇월", "몇 주", "몇주", "몇 권", "몇권", "기한", "저녁", "밤에")):
        return "schedule"
    if any(word in query for word in ("방법", "순서", "어떻게", "하는 법", "받는 법", "신청", "접수", "신고", "발급")):
        return "method"
    if re.search(r'납부|카드로.*(?:낼|내|납)|계좌이체',query):
        return 'method'
    if re.search(r'등록.*(?:하려|할|해|하나)', query):
        return 'method'
    if re.search(r'인터넷|온라인|기부', query):
        return 'method'
    if re.search(r'(?:프로그램|사업|서비스|진료).*(?:운영하|운영해|하고\s*있)', query):
        return 'services'
    if re.search(r'도움|지원|검사|상담|교육|진료|재활|접종', query) and re.search(r'받을|이용|가능|있나요', query):
        return 'services'
    if "받을 수" in query:
        return "eligibility"
    if re.search(r'넣어도|버려도|버리나요|섞어도|(?:넣으면|버리면|섞으면)(?:돼|되)|해도돼|해도되|할수없|제외되|제외품목',compact_query):
        return 'conditions'
    if re.search(r'해도|돼요|되나요|받나요|같나요|같아요|포함|가능|있어요|이용해|누구를|어디에쓰',compact_query):
        return 'services'
    return None


@lru_cache(maxsize=512)
def requested_goals(query: str) -> tuple[str, ...]:
    """Keep both requested facility fields when hours and location are asked."""
    from chatbot.query_subject import interpret_query
    query = interpret_query(query)
    primary = answer_goal(query)
    if primary in ('reference','necessity'):
        return (primary,)
    goals = [primary] if primary else []
    if asks_opening_hours(query) and 'hours' not in goals:
        goals.append('hours')
    if (asks_location(query) and 'location' not in goals
            and not re.search(r'어디에?\s*쓰|이익.*어디|어디(?:서|로).{0,6}(?:신청|접수|제출)|(?:신청|접수|예약).{0,12}어디(?:로|서)해',query.replace(' ',''))):
        goals.append('location')
    if primary != 'reference':
        extra = [('documents', r'(?:준비|구비|필요(?:한)?).*서류|서류.*(?:필요|무엇|뭐|지참)|준비물|가져가|가져갈|지참'),
                 ('eligibility', r'누가|누구|대상|조건|자격|몇\s*살|어떤\s*(?:주민|구민|사람)'),
                 ('schedule', r'언제|주기|날짜'),
                 ('method', r'어떻게|방법')]
        extra += [('cost',r'비용|발급비|수수료|요금|사용료|얼마(?!나)|얼마나\s*(?:주|지원)|공짜|무료'),
                  ('schedule',r'몇\s*(?:월|주|권|번|년|개월)|한\s*달|기한'),
                  ('conditions',r'제외|금지|제한')]
        if re.search(r'(?:발급|뽑을|출력).{0,10}수|증명서도.*(?:있나요|돼요)',query) and primary == 'cost':
            goals.append('services')
        for goal, pattern in extra:
            if (goal not in goals and re.search(pattern, query)
                    and not (goal == 'documents' and re.search(r'수거|가져가.*서비스|와서.*가져가',query))
                    and not (primary in ('precautions','hours','location','specifications','conditions') and goal == 'method')
                    and not (primary == 'method' and goal == 'cost' and re.search(r'계산|거래금액|환산',query) and not '얼마' in query)
                    and not (primary == 'conditions' and goal == 'cost' and not re.search(r'얼마|비용은|수수료는',query))
                    and not (primary == 'cost' and goal == 'method' and not re.search(r'방법|절차|어떻게|어디',query))):
                goals.append(goal)
    return tuple(goals)
