"""
멀티턴 대화 처리 모듈
- Gemini 무료 티어 기반 답변 생성
- 문맥 유지 (이전 대화 기억)
- 모호한 질문 시 역질문으로 의도 파악
- 출처 명시 답변
- 개인정보 필터링
"""

import re
import json
import time
import threading
import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from config import GROQ_API_KEY, GROQ_LLM_MODEL, CHATBOT_TEMPERATURE, MAX_CONVERSATION_HISTORY
from database_db.database import Database
from chatbot.retriever import HybridRetriever
from chatbot.dept_directory import normalize_dept_names

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 부산광역시 사하구청 공식 AI 상담사입니다.

## 역할
- 사하구청 홈페이지의 공식 정보만을 바탕으로 구민의 질문에 친절하고 정확하게 답변합니다.
- 행정 용어를 일반인이 이해하기 쉬운 직관적인 언어로 풀어서 설명합니다.

## 규칙 (반드시 준수)
1. **사실 기반 답변**: 제공된 참고자료에 있는 정보만 사용하세요. 참고자료에 없는 내용은 절대 추측하거나 지어내지 마세요.
2. **모호한 질문 처리**: 질문이 너무 넓거나 모호하면, 답변 마지막에 정확히 `[CLARIFICATION]` 토큰을 한 줄로 추가하고 구체적인 선택지를 제시하며 역질문하세요.
   예: "복지 관련 문의를 주셨네요. 혹시 다음 중 어떤 분야가 궁금하신가요? 1) 노인복지 2) 아동복지 3) 장애인복지 4) 기초생활수급\n[CLARIFICATION]"
3. **출처 명시**: 답변에 사용한 정보의 출처를 반드시 언급하세요. (예: "사하구청 홈페이지 ○○ 페이지에 따르면...")
4. **개인정보 보호**: 사용자가 주민등록번호, 전화번호 등 개인정보를 입력하면, 저장하지 않으며 입력하지 말 것을 안내하세요.
5. **정보 부족 시**: 참고자료에서 답을 찾을 수 없으면, 솔직히 "해당 정보를 찾지 못했습니다"라고 안내하고, 사하구청 대표전화(051-220-4000)나 홈페이지 방문을 권장하세요.
6. **답변 형식**: 핵심 내용을 먼저 간결하게 답한 뒤, 필요하면 세부사항을 보충하세요.

## 참고자료
{context}
"""

# 개인정보 패턴 (탐지 + 마스킹)
PERSONAL_INFO_PATTERNS = [
    (re.compile(r"\d{6}[-\s]?\d{7}"), "주민등록번호"),
    (re.compile(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}"), "전화번호"),
    (re.compile(r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"), "카드번호"),
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "이메일"),
]

ADDRESS_PATTERNS = [
    re.compile(r"[가-힣]{1,20}(?:동|읍|면|리)\s*\d{1,4}(?:-\d{1,4})?(?:\s*(?:번지|호|층))?"),
    re.compile(r"[가-힣]{1,20}(?:로|길)\s*\d{1,4}(?:-\d{1,4})?(?:\s*(?:번지|호|층))?"),
]

CLARIFICATION_TAG = "[CLARIFICATION]"
ANSWER_STYLE_SUFFIX = """

Answer style:
- Keep replies concise and conversational.
- Prefer 3 to 5 short bullet points for actionable guidance.
- Do not repeat the same sentence, phone number, or paragraph.
- If the user asks about a street/manhole issue, give the report steps once and avoid boilerplate repetition.
- Do not mix in foreign-language phrases such as Japanese or other non-Korean text.
"""


def detect_personal_info(text: str, use_ner: bool = True) -> str | None:
    """
    텍스트에서 첫 번째로 매칭된 개인정보 유형 반환 (없으면 None).
    입력 차단은 정형 개인정보와 상세주소만 검사하고,
    동 이름 같은 일반 지역명은 막지 않는다.
    """
    for pattern, info_type in PERSONAL_INFO_PATTERNS:
        if pattern.search(text):
            return info_type

    for pattern in ADDRESS_PATTERNS:
        if pattern.search(text):
            return "주소"

    if use_ner:
        try:
            from chatbot.pii_detector import NERPIIDetector
            _, ner_found = NERPIIDetector().detect_and_mask(text)
            if ner_found:
                return ner_found[0]
        except Exception as e:
            logger.warning(f"NER 탐지 호출 실패 (정규식만 사용): {e}")

    return None


def mask_personal_info(text: str, use_ner: bool = True) -> tuple[str, list[str]]:
    """
    텍스트의 개인정보를 [MASKED:<유형>]으로 치환하고 (마스킹된 텍스트, 발견된 유형 목록) 반환.
    LLM 응답이 크롤링 데이터에 포함된 개인정보를 그대로 노출하지 않도록 출력단에서 호출.

    정규식과 NER을 병렬 적용하여 정형/비정형 PII를 모두 차단.
    """
    found: list[str] = []
    masked = text

    # 1단계: 정규식 기반 정형 PII (전화번호, 주민번호 등)
    for pattern, info_type in PERSONAL_INFO_PATTERNS:
        if pattern.search(masked):
            found.append(info_type)
            masked = pattern.sub(f"[MASKED:{info_type}]", masked)

    # 2단계: NER 기반 비정형 PII (이름, 주소 등)
    if use_ner:
        try:
            from chatbot.pii_detector import NERPIIDetector
            masked, ner_found = NERPIIDetector().detect_and_mask(masked)
            found.extend(ner_found)
        except Exception as e:
            logger.warning(f"NER 마스킹 호출 실패 (정규식 결과만 반환): {e}")

    return masked, found


def strip_foreign_script(text: str) -> str:
    """Remove stray Japanese kana and similar foreign-script fragments from replies."""
    if not text:
        return text

    cleaned = re.sub(r"[\u3040-\u30ff\u31f0-\u31ff]", "", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def enforce_official_contact(answer: str, user_message: str, sources: list[dict]) -> str:
    """For department/contact questions, force the official staff-directory phone number."""
    if not answer or not sources:
        return answer

    query = (user_message or "").lower()
    if not any(keyword in query for keyword in ["담당", "부서", "연락", "전화", "번호", "문의"]):
        return answer

    official_source = next(
        (
            source for source in sources
            if (source.get("contact") or "").strip()
            and (
                source.get("category") == "staff_directory"
                or "staff/list.do" in (source.get("url") or "")
            )
        ),
        None,
    )
    if not official_source:
        return answer

    official_contact = official_source["contact"].strip()
    if not official_contact:
        return answer

    phone_pattern = re.compile(r"0\d{1,2}-\d{3,4}-\d{4}")
    phone_matches = phone_pattern.findall(answer)

    if phone_matches:
        for phone in set(phone_matches):
            answer = answer.replace(phone, official_contact)
        return answer

    dept_name = (official_source.get("department") or "").strip()
    if dept_name and official_contact not in answer:
        answer += f"\n\n공식 직원업무안내 기준 {dept_name} 연락처는 {official_contact}입니다."

    return answer


class ChatBot:
    def __init__(self):
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY를 .env에 설정해주세요")

        self.llm = ChatGroq(
            model=GROQ_LLM_MODEL,
            api_key=GROQ_API_KEY,
            temperature=CHATBOT_TEMPERATURE,
            max_retries=1,
        )
        self.retriever = HybridRetriever()
        self.db = Database()
        self._last_call_time = 0
        # 스레드풀에서 동일 싱글턴 봇을 공유하므로 호출 간격 갱신을 락으로 보호
        self._call_lock = threading.Lock()

        # NER PII 탐지기 사전 로딩 (첫 요청 지연 방지)
        try:
            from chatbot.pii_detector import NERPIIDetector
            NERPIIDetector()
        except Exception as e:
            logger.warning(f"NER 탐지기 사전 로딩 실패 (필요 시 지연 로딩): {e}")

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT + ANSWER_STYLE_SUFFIX),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ])

        self.chain = self.prompt | self.llm
        logger.info("챗봇 초기화 완료")

    def _check_personal_info(self, text: str) -> str | None:
        """개인정보 입력 감지 (하위 호환용 래퍼)"""
        return detect_personal_info(text, use_ner=False)

    def _build_history(self, conversation: list[dict]) -> list:
        """대화 이력을 LangChain 메시지 형식으로 변환"""
        messages = []
        for msg in conversation:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        return messages

    def chat(self, session_id: str, user_message: str) -> dict:
        """
        사용자 메시지 처리 → 답변 생성

        Returns:
            {
                "answer": str,        # AI 답변
                "sources": list,      # 출처 목록 [{title, url, category}]
                "is_clarification": bool,  # 역질문 여부
            }
        """
        # 1. 개인정보 체크
        personal_info = self._check_personal_info(user_message)
        if personal_info:
            warning = (
                f"⚠️ 입력하신 내용에 {personal_info}(으)로 보이는 개인정보가 포함되어 있습니다.\n\n"
                "개인정보 보호를 위해 채팅창에 개인정보를 입력하지 말아주세요. "
                "입력하신 정보는 저장되지 않습니다.\n\n"
                "개인정보가 필요한 업무는 사하구청을 직접 방문하시거나 "
                "대표전화(051-220-4000)로 문의해주세요."
            )
            return {
                "answer": warning,
                "sources": [],
                "is_clarification": False,
                "degraded": False,
                "degraded_reason": None,
            }

        # 2. 대화 이력 조회
        history = self.db.get_conversation_history(session_id, limit=MAX_CONVERSATION_HISTORY)
        langchain_history = self._build_history(history)

        # 3. 하이브리드 검색 (문맥 포함 검색어 구성)
        search_query = user_message
        if history:
            recent = [m["content"] for m in history[-2:] if m["role"] == "user"]
            if recent:
                search_query = " ".join(recent + [user_message])

        search_outcome = self.retriever.search(search_query)
        results = search_outcome["results"]
        degraded = search_outcome["degraded"]
        degraded_reason = search_outcome["reason"]
        context, sources = self.retriever.format_context(user_message, results)

        if not context:
            context = "(관련 참고자료를 찾지 못했습니다)"

        # 4. LLM 답변 생성 (무료 티어 속도 제한: 최소 4초 간격)
        #    호출 간격 계산·갱신만 락으로 보호하고, 갱신 직후 락을 풀어
        #    실제 네트워크 호출(invoke)은 락 밖에서 수행한다.
        #    → 연속 호출이 4초 이상 간격으로 "시작"되도록 보장하면서도,
        #      느린 LLM 응답 동안 다른 요청이 불필요하게 막히지 않게 한다.
        with self._call_lock:
            elapsed = time.time() - self._last_call_time
            if elapsed < 4:
                time.sleep(4 - elapsed)
            self._last_call_time = time.time()

        try:
            response = self.chain.invoke({
                "context": context,
                "history": langchain_history,
                "question": user_message,
            })
            answer = response.content
        except Exception as e:
            logger.error(f"LLM 답변 생성 실패: {e}")
            answer = (
                "죄송합니다. 일시적으로 답변을 생성하지 못했습니다.\n"
                "잠시 후 다시 시도해주시거나, 사하구청 대표전화(051-220-4000)로 문의해주세요."
            )
            sources = []
            degraded = True
            degraded_reason = "llm_failed"

        # 5. 역질문 여부 판단 ([CLARIFICATION] 태그 우선, 키워드 폴백)
        is_clarification = CLARIFICATION_TAG in answer
        if is_clarification:
            answer = answer.replace(CLARIFICATION_TAG, "").strip()
        else:
            # LLM이 태그를 빠뜨린 경우 키워드 휴리스틱으로 폴백
            is_clarification = any(kw in answer for kw in [
                "어떤 분야", "어떤 것이", "구체적으로", "선택해",
                "궁금하신가요?", "알려주시겠어요"
            ])

        # 역질문(되묻기) 응답에는 아직 '답변'이 없으므로 출처를 표시하지 않는다.
        # (관련성 낮은 폴백 출처가 역질문에 붙어 혼란을 주는 것을 방지)
        if is_clarification:
            sources = []

        # 6. 부서명 오기 보정 (예: '도로과' → '도로정비과', 공식 조직도 기준)
        answer = normalize_dept_names(answer)
        answer = enforce_official_contact(answer, user_message, sources)

        answer = strip_foreign_script(answer)
        # 7. LLM 응답 PII 마스킹 (크롤링 데이터에 섞여 들어온 개인정보 차단)
        answer, leaked = mask_personal_info(answer)
        if leaked:
            logger.warning(f"LLM 응답에서 개인정보 감지/마스킹: {leaked}")

        # 8. 대화 이력 저장
        self.db.save_conversation(session_id, "user", user_message)
        self.db.save_conversation(
            session_id, "assistant", answer,
            sources=json.dumps([s["url"] for s in sources], ensure_ascii=False) if sources else None,
        )

        return {
            "answer": answer,
            "sources": sources,
            "is_clarification": is_clarification,
            "degraded": degraded,
            "degraded_reason": degraded_reason,
        }

    def clear_session(self, session_id: str):
        """대화 초기화"""
        self.db.clear_conversation(session_id)
