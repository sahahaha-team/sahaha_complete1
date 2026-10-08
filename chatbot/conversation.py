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
from langchain_core.messages import HumanMessage, AIMessage

from config import (
    OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_NUM_CTX,
    OLLAMA_KEEP_ALIVE, CHATBOT_TEMPERATURE, CHATBOT_MAX_TOKENS,
    MAX_CONVERSATION_HISTORY, SOURCE_ONLY_ANSWERS,
    CONFIDENCE_MIN_SIMILARITY, LOW_CONFIDENCE_MESSAGE, PERSIST_CONVERSATIONS,
)
from database_db.database import Database
from chatbot.retriever import HybridRetriever
from chatbot.dept_directory import REP_PHONE, is_staff_lookup
from chatbot.response_helpers import (
    build_clarification,
    build_contextual_search_query,
    build_suggested_questions,
    is_obviously_out_of_domain,
)
from chatbot.privacy import detect_personal_info, mask_personal_info
from chatbot.verified_facts import answer_verified_table_question
from chatbot.faq_targets import match_official_page
from chatbot.source_answers import build_source_answer
from chatbot.emergency_guidance import answer_emergency_question
from chatbot.query_subject import normalize_query
from chatbot.response_helpers import resolve_clarification_reply
from chatbot.concise_answers import concise_source_answer, scope_question
from chatbot.grounded_planner import answer_with_grounded_model

logger = logging.getLogger(__name__)

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
                "evidence": {"status": "clarification", "label": "문의 범위 확인", "official_source_count": 0,
                             "answer_method": clarification.get("answer_method", "clarification")},
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

        # 3. 하이브리드 검색 (문맥 포함 검색어 구성)
        search_query = normalize_query(build_contextual_search_query(resolved_message, history))

        target_url = None if is_staff_lookup(search_query) else match_official_page(search_query)
        search_outcome = (
            self.retriever.search_official_url(search_query, target_url, k=15)
            if target_url else self.retriever.search(search_query, k=15)
        )
        if target_url and not search_outcome["results"]:
            search_outcome = self.retriever.search(search_query, k=15)
        fresh_results = self.retriever.filter_fresh_results(search_query, search_outcome["results"])
        results = self.retriever.select_grounded_results(search_query, fresh_results, limit=15)
        logger.info("상담 근거 단계: 검색=%s, 최근 확인=%s, 서로 다른 근거 URL=%s",
            len(search_outcome["results"]), len(fresh_results), len(results))
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

        grounded_results = self.retriever.select_grounded_results(search_query, results, limit=15)
        # General questions use Gemma to choose complete evidence and conditions.
        # Static emergency/contact/table routes above keep their fast response.
        planned = None if SOURCE_ONLY_ANSWERS else answer_with_grounded_model(
            search_query, grounded_results, self.retriever.db.client,
            self.retriever._content_keywords(search_query), self.llm)
        if planned and planned["is_clarification"]:
            return self._clarification_result(session_id, user_message, search_query, planned)
        if planned:
            concise = planned
            used_results = planned["documents"]
            method = "grounded_model"
        else:
            original, used_results = build_source_answer(grounded_results, self.retriever.db.client,
                query=search_query, topic_keywords=self.retriever._content_keywords(search_query), require_brief=True)
            if not original:
                return {
                    "answer": LOW_CONFIDENCE_MESSAGE, "sources": [], "is_clarification": False,
                    "degraded": True, "degraded_reason": "no_current_evidence",
                    "evidence": {"status": "insufficient", "label": "최신 근거를 찾지 못함", "official_source_count": 0},
                    "suggested_questions": [],
                }
            concise = concise_source_answer(search_query, original, used_results,
                self.retriever._content_keywords(search_query))
            if concise["is_clarification"]:
                return self._clarification_result(session_id, user_message, search_query, concise)
            method = "source_extract" if SOURCE_ONLY_ANSWERS else "source_fallback"
        answer, _ = mask_personal_info(concise["answer"], use_ner=False)
        details, _ = mask_personal_info(concise.get("answer_details", ""), use_ner=False)
        _context, sources = self.retriever.format_context(search_query, used_results)
        for source in sources:
            if source.get("category") != "staff_directory":
                source["department"] = ""
                source["contact"] = ""
        self._save_conversation_safe(session_id, "user", user_message, search_query=search_query)
        self._save_conversation_safe(session_id, "assistant", answer,
            sources=json.dumps([source["url"] for source in sources], ensure_ascii=False))
        return {
            "answer": answer, "answer_details": details, "sources": sources, "is_clarification": False,
            "degraded": degraded, "degraded_reason": degraded_reason,
            "evidence": {"status": "official", "label": "공식 자료 핵심 안내",
                         "official_source_count": len(sources), "answer_method": method},
            "suggested_questions": build_suggested_questions(search_query, sources),
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
