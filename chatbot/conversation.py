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
import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from config import GROQ_API_KEY, GROQ_LLM_MODEL, CHATBOT_TEMPERATURE, MAX_CONVERSATION_HISTORY
from database_db.database import Database
from chatbot.retriever import HybridRetriever

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 부산광역시 사하구청 공식 AI 상담사입니다.

## 역할
- 사하구청 홈페이지의 공식 정보만을 바탕으로 구민의 질문에 친절하고 정확하게 답변합니다.
- 행정 용어를 일반인이 이해하기 쉬운 직관적인 언어로 풀어서 설명합니다.

## 규칙 (반드시 준수)
1. **사실 기반 답변**: 제공된 참고자료에 있는 정보만 사용하세요. 참고자료에 없는 내용은 절대 추측하거나 지어내지 마세요.
2. **모호한 질문 처리**: 질문이 너무 넓거나 모호하면, 바로 답변하지 말고 구체적인 선택지를 제시하며 역질문하세요.
   예: "복지 관련 문의를 주셨네요. 혹시 다음 중 어떤 분야가 궁금하신가요? 1) 노인복지 2) 아동복지 3) 장애인복지 4) 기초생활수급"
3. **출처 명시**: 답변에 사용한 정보의 출처를 반드시 언급하세요. (예: "사하구청 홈페이지 ○○ 페이지에 따르면...")
4. **개인정보 보호**: 사용자가 주민등록번호, 전화번호 등 개인정보를 입력하면, 저장하지 않으며 입력하지 말 것을 안내하세요.
5. **정보 부족 시**: 참고자료에서 답을 찾을 수 없으면, 솔직히 "해당 정보를 찾지 못했습니다"라고 안내하고, 사하구청 대표전화(051-220-4000)나 홈페이지 방문을 권장하세요.
6. **답변 형식**: 핵심 내용을 먼저 간결하게 답한 뒤, 필요하면 세부사항을 보충하세요.

## 참고자료
{context}
"""

# 개인정보 패턴
PERSONAL_INFO_PATTERNS = [
    (r"\d{6}[-\s]?\d{7}", "주민등록번호"),
    (r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}", "전화번호"),
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "이메일"),
]


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

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ])

        self.chain = self.prompt | self.llm
        logger.info("챗봇 초기화 완료")

    def _check_personal_info(self, text: str) -> str | None:
        """개인정보 입력 감지"""
        for pattern, info_type in PERSONAL_INFO_PATTERNS:
            if re.search(pattern, text):
                return info_type
        return None

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

        results = self.retriever.search(search_query)
        context, sources = self.retriever.format_context(results)

        if not context:
            context = "(관련 참고자료를 찾지 못했습니다)"

        # 4. LLM 답변 생성 (무료 티어 속도 제한: 최소 4초 간격)
        elapsed = time.time() - self._last_call_time
        if elapsed < 4:
            time.sleep(4 - elapsed)

        try:
            self._last_call_time = time.time()
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

        # 5. 역질문 여부 판단
        is_clarification = any(kw in answer for kw in ["어떤 분야", "어떤 것이", "구체적으로", "선택해", "궁금하신가요?", "알려주시겠어요"])

        # 6. 대화 이력 저장
        self.db.save_conversation(session_id, "user", user_message)
        self.db.save_conversation(
            session_id, "assistant", answer,
            sources=json.dumps([s["url"] for s in sources], ensure_ascii=False) if sources else None,
        )

        return {
            "answer": answer,
            "sources": sources,
            "is_clarification": is_clarification,
        }

    def clear_session(self, session_id: str):
        """대화 초기화"""
        self.db.clear_conversation(session_id)
