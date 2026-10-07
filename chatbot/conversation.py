"""
멀티턴 대화 처리 모듈
- 로컬 Ollama 기반 답변 생성
- 문맥 유지 (이전 대화 기억)
- 모호한 질문 시 역질문으로 의도 파악
- 출처 명시 답변
- 개인정보 필터링
"""

import re
import json
import threading
import logging
import time
from collections import OrderedDict
try:
    from langchain_ollama import ChatOllama
except ImportError:  # 구버전 환경 호환
    from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from config import (
    OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_NUM_CTX,
    OLLAMA_KEEP_ALIVE, CHATBOT_TEMPERATURE, CHATBOT_MAX_TOKENS,
    MAX_CONVERSATION_HISTORY, SOURCE_ONLY_ANSWERS,
    CONFIDENCE_MIN_SIMILARITY, LOW_CONFIDENCE_MESSAGE, PERSIST_CONVERSATIONS,
)
from database_db.database import Database
from chatbot.retriever import HybridRetriever
from chatbot.dept_directory import normalize_dept_names, REP_PHONE, is_staff_lookup
from chatbot.response_helpers import (
    build_clarification,
    build_contextual_search_query,
    build_suggested_questions,
    is_obviously_out_of_domain,
)
from chatbot.privacy import detect_personal_info, mask_personal_info
from chatbot.evidence import unsupported_numbers
from chatbot.verified_facts import answer_verified_table_question
from chatbot.faq_targets import match_official_page
from chatbot.source_answers import build_source_answer
from chatbot.emergency_guidance import answer_emergency_question
from chatbot.query_subject import normalize_query
from chatbot.response_helpers import resolve_clarification_reply
from chatbot.concise_answers import concise_source_answer, scope_question
from chatbot.answer_completion import model_answer_complete

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 부산광역시 사하구청 공식 AI 상담사입니다.

## 역할
- 사하구청 홈페이지의 확인된 본문과 담당자가 제공한 기간 명시 보고서만을 바탕으로 답변합니다.
- 행정 용어를 일반인이 이해하기 쉬운 직관적인 언어로 풀어서 설명합니다.

## 규칙 (반드시 준수)
1. **사실 기반 답변**: 제공된 참고자료에 있는 정보만 사용하세요. 참고자료에 없는 내용은 절대 추측하거나 지어내지 마세요.
2. **구체적인 정보 직접 제공**: 검색된 문서에 사용자가 묻는 구체적인 정보(예: 배출 요일, 시간, 장소, 방법 등)가 있다면, "홈페이지를 확인하라"는 식의 회피성 답변을 하지 마세요. 해당 정보를 글머리 기호(블릿)를 사용하여 이해하기 쉽게 직접 요약해 제공해야 합니다.
3. **질문 범위 확인**: 대상·신청 유형에 따라 안내가 달라지거나 요청 범위가 넓으면 한 가지 조건을 먼저 물으세요. 명확한 질문에는 짧게 답하세요.
4. **출처 명시**: 답변에 사용한 정보의 출처를 반드시 언급하세요. (예: "사하구청 홈페이지 ○○ 페이지에 따르면...")
5. **개인정보 보호**: 사용자가 주민등록번호, 전화번호 등 개인정보를 입력하면, 저장하지 않으며 입력하지 말 것을 안내하세요.
6. **정보 부족 시**: 참고자료에서 답을 찾을 수 없으면, 솔직히 "해당 정보를 찾지 못했습니다"라고 안내하고, 사하구청 대표전화(051-220-4000)나 홈페이지 방문을 권장하세요.
7. **답변 형식 및 하이라이트(강조) 규칙**: 핵심 내용을 먼저 간결하게 답한 뒤, 세부사항을 보충하세요. 단, **인사말이나 첫 문장, 단순 개요에는 절대 볼드체(강조)를 사용하지 마세요.** 구민에게 실질적으로 필요한 **핵심 데이터(전화번호, 담당 부서명, 필수 지참 서류, 기한, 장소, 금액 등)에만** 제한적으로 볼드체를 적용하세요.
8. **시간 범위**: 분석 보고서 수치는 자료 기준 기간의 과거 통계로만 설명하세요. 보고서 작성 연도를 통계 대상 연도로 바꾸지 마세요. 현재 수수료·지원금·운영시간을 과거 보고서로 답하지 마세요.
9. **검증**: 이전 대화나 검색용 질문은 사실 근거가 아닙니다. 현재 참고자료 본문에 없는 숫자·날짜·부서·절차는 말하지 마세요. 상충하는 자료가 있으면 단정하지 말고 확인이 필요하다고 답하세요.


## 참고자료
{context}
"""

CLARIFICATION_TAG = "[CLARIFICATION]"
ANSWER_STYLE_SUFFIX = """

Answer style:
- Keep replies concise and conversational.
- Answer the precise question in 2 to 3 short sentences or at most 3 short bullets.
- Keep important qualifications and exceptions beside the fact they qualify.
- Finish every sentence within the reply budget; never start a point that you cannot finish.
- If several services or conditions could apply, ask one focused clarification question before answering.
- Do not repeat the same sentence, phone number, or paragraph.
- If the user asks about a street/manhole issue, give the report steps once and avoid boilerplate repetition.
- Do not mix in foreign-language phrases such as Japanese or other non-Korean text.
"""


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
    if not answer:
        return answer

    query = (user_message or "").lower()

    # 대표전화/대표번호 질문은 특정인 직통번호(예: 구청장 051-220-4001)가 아니라
    # 공식 대표번호(051-220-4000)로 고정한다. (직원검색이 '사하구청장'을 매칭해
    # 대표전화로 4001을 잘못 안내하던 문제 방지)
    if any(k in query for k in ["대표전화", "대표 전화", "대표번호", "대표 번호", "대표 연락처", "대표연락처"]):
        phone_pattern = re.compile(r"0\d{1,2}-\d{3,4}-\d{4}")
        if phone_pattern.search(answer):
            answer = phone_pattern.sub(REP_PHONE, answer)
        elif REP_PHONE not in answer:
            answer += f"\n\n사하구청 대표전화는 {REP_PHONE}입니다."
        return answer

    if not sources:
        return answer
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
        self.llm = ChatOllama(
            base_url=OLLAMA_BASE_URL,
            model=OLLAMA_MODEL,
            temperature=CHATBOT_TEMPERATURE,
            num_predict=CHATBOT_MAX_TOKENS,
            num_ctx=OLLAMA_NUM_CTX,
            timeout=OLLAMA_TIMEOUT,
            keep_alive=OLLAMA_KEEP_ALIVE,
        )
        self.retriever = HybridRetriever()
        # 기본은 개인정보 최소수집을 위해 프로세스 메모리에서만 문맥을 유지한다.
        # 영구 저장을 명시적으로 켠 경우에만 service role로 DB에 기록한다.
        self.db = Database(admin=True) if PERSIST_CONVERSATIONS else None
        self._memory_history: dict[str, list[dict]] = {}
        self._history_lock = threading.RLock()
        self._pending_clarifications = OrderedDict()

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

    def _get_history_safe(self, session_id: str) -> list[dict]:
        """DB 장애가 챗봇 전체 500 오류로 번지지 않도록 빈 이력으로 폴백한다."""
        if self.db is None:
            with self._history_lock:
                return list(self._memory_history.get(session_id, []))[-MAX_CONVERSATION_HISTORY:]
        try:
            return self.db.get_conversation_history(
                session_id, limit=MAX_CONVERSATION_HISTORY
            )
        except Exception as exc:
            logger.warning(f"대화 이력 조회 실패 (빈 이력으로 계속): {exc}")
            return []

    def _save_conversation_safe(
        self, session_id: str, role: str, content: str, sources: str = None, search_query: str = None
    ) -> None:
        """대화 로그 저장 실패는 기록하되 사용자 답변 자체는 유지한다."""
        if self.db is None:
            with self._history_lock:
                history = self._memory_history.setdefault(session_id, [])
                history.append({"role": role, "content": content, "sources": sources, "search_query": search_query})
                del history[:-MAX_CONVERSATION_HISTORY]
            return
        try:
            self.db.save_conversation(session_id, role, content, sources=sources)
        except Exception as exc:
            logger.warning(f"대화 이력 저장 실패 ({role}): {exc}")

    def remember_contact_exchange(self, session_id: str, user_message: str, result: dict):
        """Keep local contact replies in the normal memory history without DB I/O."""
        self._clear_pending_clarification(session_id)
        if self.db is None and result.get("evidence", {}).get("status") != "protected":
            self._save_conversation_safe(session_id, "user", user_message)
            self._save_conversation_safe(session_id, "assistant", result["answer"],
                                         sources=json.dumps(result.get("sources", []), ensure_ascii=False))

    def _clear_pending_clarification(self, session_id: str):
        with self._history_lock:
            getattr(self, "_pending_clarifications", {}).pop(session_id, None)

    def contextual_message(self, session_id: str, message: str) -> str:
        with self._history_lock:
            pending = getattr(self, "_pending_clarifications", {}).get(session_id)
            if pending and time.monotonic() - pending["created_at"] > 1800:
                self._pending_clarifications.pop(session_id, None)
                pending = None
            if pending:
                return resolve_clarification_reply(message, pending)
            history = list(self._memory_history.get(session_id, [])) if self.db is None else []
            return build_contextual_search_query(message, history)

    def _clarification_result(self, session_id: str, user_message: str, query: str, clarification: dict) -> dict:
        with self._history_lock:
            if not hasattr(self, "_pending_clarifications"):
                self._pending_clarifications = OrderedDict()
            self._pending_clarifications[session_id] = {
                **clarification, "query": query, "created_at": time.monotonic()}
            self._pending_clarifications.move_to_end(session_id)
            while len(self._pending_clarifications) > 1000:
                self._pending_clarifications.popitem(last=False)
        self._save_conversation_safe(session_id, "user", user_message, search_query=query)
        self._save_conversation_safe(session_id, "assistant", clarification["answer"])
        return {"answer": clarification["answer"], "sources": [], "is_clarification": True,
                "degraded": False, "degraded_reason": None,
                "evidence": {"status": "clarification", "label": "문의 범위 확인", "official_source_count": 0},
                "suggested_questions": clarification["suggested_questions"]}

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
        # Fire reporting takes priority. Do not echo or retain incident locations
        # or personal data; the same official guidance works without models/DB.
        emergency_result = answer_emergency_question(user_message)
        if emergency_result is not None:
            self._clear_pending_clarification(session_id)
            return emergency_result

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
                "evidence": {"status": "protected", "label": "개인정보 보호됨", "official_source_count": 0},
                "suggested_questions": [],
            }

        # 1-1. 주가·코인 예측 등 명백한 비행정 요청은 공식 문서의 단어가 우연히
        # 겹치더라도 검색/LLM으로 넘기지 않는다. 이는 답변 생성 이전의 환각 차단선이다.
        if is_obviously_out_of_domain(user_message):
            return {
                "answer": LOW_CONFIDENCE_MESSAGE,
                "sources": [],
                "is_clarification": False,
                "degraded": True,
                "degraded_reason": "out_of_domain",
                "evidence": {
                    "status": "out_of_domain",
                    "label": "사하구 행정 상담 범위 밖",
                    "official_source_count": 0,
                },
                "suggested_questions": ["사하구 민원 안내해줘", "사하구 복지 지원 알려줘"],
            }

        resolved_message = self.contextual_message(session_id, user_message)
        self._clear_pending_clarification(session_id)
        from chatbot.contact_directory import contact_responder
        contact_result = contact_responder.respond(session_id, resolved_message)
        if contact_result is not None:
            self.remember_contact_exchange(session_id, user_message, contact_result)
            return contact_result

        # 1-2. 너무 포괄적인 요청은 임의로 답하지 않고 먼저 범위를 좁힌다.
        clarification = build_clarification(resolved_message)
        if clarification:
            return self._clarification_result(session_id, user_message, resolved_message, clarification)

        # 비용표처럼 한 페이지에 여러 사업의 금액이 있는 경우, 오늘 확인된
        # 공식 표의 해당 행만 읽어 답한다. 행 구조가 바뀌면 추측하지 않는다.
        verified = answer_verified_table_question(resolved_message, self.retriever.db.client)
        if verified is not None:
            verified_details, _ = mask_personal_info(verified.get("answer_details", ""), use_ner=False)
            self._save_conversation_safe(session_id, "user", user_message, search_query=resolved_message)
            self._save_conversation_safe(session_id, "assistant", verified["answer"])
            return {
                "answer": verified["answer"], "answer_details": verified_details, "sources": verified["sources"],
                "is_clarification": False, "degraded": not verified["verified"],
                "degraded_reason": None if verified["verified"] else "unverified_table",
                "evidence": {
                    "status": "official" if verified["verified"] else "insufficient",
                    "label": "최근 공식 표의 해당 항목 확인됨" if verified["verified"] else "현재 표의 항목 확인 필요",
                    "official_source_count": len(verified["sources"]),
                },
                "suggested_questions": [],
            }

        # 2. 대화 이력 조회
        history = self._get_history_safe(session_id)
        langchain_history = self._build_history(history)

        # 3. 하이브리드 검색 (문맥 포함 검색어 구성)
        search_query = normalize_query(build_contextual_search_query(resolved_message, history))

        target_url = None if is_staff_lookup(search_query) else match_official_page(search_query)
        search_outcome = (
            self.retriever.search_official_url(search_query, target_url, k=15)
            if target_url else self.retriever.search(search_query, k=15)
        )
        fresh_results = self.retriever.filter_fresh_results(search_query, search_outcome["results"])
        results = self.retriever.select_grounded_results(search_query, fresh_results, limit=5)
        degraded = search_outcome["degraded"]
        degraded_reason = search_outcome["reason"]

        # 3-1. 지역·신청 표현을 제외한 질문 핵심 업무가 개별 공식 문서에 있어야 한다.
        #      점수만 높고 실제 업무가 다른 결과는 답변이나 LLM에 전달하지 않는다.
        evidence = self.retriever.assess_evidence(search_query, results)
        if not evidence["confident"]:
            top_sim = evidence["top_similarity"]
            logger.info(f"핵심 업무 근거 없음 (참고용 최상위 유사도={top_sim:.2f}) → 안전 안내 출력")
            self._save_conversation_safe(session_id, "user", user_message, search_query=search_query)
            self._save_conversation_safe(session_id, "assistant", LOW_CONFIDENCE_MESSAGE)
            return {
                "answer": LOW_CONFIDENCE_MESSAGE,
                "sources": [],
                "is_clarification": False,
                "degraded": True,
                "degraded_reason": "low_confidence",
                "evidence": {
                    "status": evidence["status"],
                    "label": evidence["label"],
                    "official_source_count": evidence["official_source_count"],
                },
                "suggested_questions": ["사하구청 대표전화 알려줘", "민원 담당 부서 안내해줘"],
            }

        grounded_results = self.retriever.select_grounded_results(search_query, results)
        if SOURCE_ONLY_ANSWERS:
            answer, used_results = build_source_answer(grounded_results, self.retriever.db.client,
                query=search_query, topic_keywords=self.retriever._content_keywords(search_query))
            if answer:
                concise = concise_source_answer(search_query, answer, used_results,
                    self.retriever._content_keywords(search_query))
                if concise["is_clarification"]:
                    return self._clarification_result(session_id, user_message, search_query, concise)
                answer = concise["answer"]
                answer_details, _ = mask_personal_info(concise["answer_details"], use_ner=False)
                _context, sources = self.retriever.format_context(search_query, used_results)
                # Old model-tagged department/contact metadata is not an
                # independently verified fact. Only staff-directory records
                # carry contact badges in source-only replies.
                for source in sources:
                    if source.get("category") != "staff_directory":
                        source["department"] = ""
                        source["contact"] = ""
                answer, _leaked = mask_personal_info(answer, use_ner=False)
                self._save_conversation_safe(session_id, "user", user_message, search_query=search_query)
                self._save_conversation_safe(session_id, "assistant", answer,
                    sources=json.dumps([source["url"] for source in sources], ensure_ascii=False))
                return {
                    "answer": answer, "answer_details": answer_details, "sources": sources, "is_clarification": False,
                    "degraded": degraded, "degraded_reason": degraded_reason,
                    "evidence": {"status": "official", "label": "공식 자료 핵심 안내",
                                 "official_source_count": len(sources)},
                    "suggested_questions": build_suggested_questions(search_query, sources),
                }
            grounded_results = []
        context, sources = self.retriever.format_context(user_message, grounded_results)

        if not context:
            return {
                "answer": LOW_CONFIDENCE_MESSAGE, "sources": [], "is_clarification": False,
                "degraded": True, "degraded_reason": "no_current_evidence",
                "evidence": {"status": "insufficient", "label": "최신 근거를 찾지 못함", "official_source_count": 0},
                "suggested_questions": [],
            }

        # 4. 로컬 Ollama 답변 생성 (외부 API 키·무료 티어 제한 없음)
        try:
            response = self.chain.invoke({
                "context": context,
                "history": langchain_history,
                "question": user_message,
            })
            answer = response.content
            if not model_answer_complete(answer, getattr(response, "response_metadata", None)):
                # A second generation could be long or invent the missing
                # conclusion. Ask for a narrower request without exposing
                # the cut-off claim or dropping a possible final exception.
                return self._clarification_result(session_id, user_message, search_query,
                    scope_question(search_query, context))
        except Exception as e:
            logger.error(f"LLM 답변 생성 실패: {e}")
            answer = (
                "죄송합니다. 일시적으로 답변을 생성하지 못했습니다.\n"
                "잠시 후 다시 시도해주시거나, 사하구청 대표전화(051-220-4000)로 문의해주세요."
            )
            sources = []
            degraded = True
            degraded_reason = "llm_failed"

        source_fact_text = "\n".join(str(doc.get("content") or "") for doc in grounded_results)
        if degraded_reason != "llm_failed" and unsupported_numbers(answer, source_fact_text + "\n" + REP_PHONE):
            logger.warning("답변의 숫자가 검색 근거에 없어 답변 차단")
            answer = LOW_CONFIDENCE_MESSAGE
            sources = []
            degraded = True
            degraded_reason = "unsupported_fact"

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
        # 전화·이메일·주민번호 등 명시 패턴은 즉시 마스킹한다. 범용 NER는 CPU에서
        # 응답마다 수십 초가 걸리고 공개 담당자명까지 오탐할 수 있어 기본 응답 경로에서는
        # 사용하지 않는다. 사용자 입력은 저장되지 않으며 동일한 정규식 검사를 먼저 거친다.
        answer, leaked = mask_personal_info(answer, use_ner=False)
        if leaked:
            logger.warning(f"LLM 응답에서 개인정보 감지/마스킹: {leaked}")

        # 8. 대화 이력 저장
        self._save_conversation_safe(session_id, "user", user_message, search_query=search_query)
        self._save_conversation_safe(
            session_id, "assistant", answer,
            sources=json.dumps([s["url"] for s in sources], ensure_ascii=False) if sources else None,
        )

        return {
            "answer": answer,
            "sources": sources,
            "is_clarification": is_clarification,
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "evidence": {
                "status": "insufficient" if degraded_reason == "unsupported_fact" else ("unavailable" if degraded_reason == "llm_failed" else evidence["status"]),
                "label": "답변 근거 확인 필요" if degraded_reason == "unsupported_fact" else ("답변 생성 일시 중단" if degraded_reason == "llm_failed" else evidence["label"]),
                "official_source_count": len(sources),
            },
            "suggested_questions": [] if is_clarification else build_suggested_questions(user_message, sources),
        }

    def clear_session(self, session_id: str):
        """대화 초기화"""
        self._clear_pending_clarification(session_id)
        if self.db is None:
            with self._history_lock:
                self._memory_history.pop(session_id, None)
            return
        try:
            self.db.clear_conversation(session_id)
        except Exception as exc:
            logger.warning(f"대화 이력 초기화 실패: {exc}")
