"""
LLM 기반 메타데이터 자동 태깅 (Groq - 무료 티어)
- 청크별 서비스 분류, 대상, 키워드 추출
"""

import json
import time
import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate

from config import GROQ_API_KEY, GROQ_LLM_MODEL

logger = logging.getLogger(__name__)

TAGGING_PROMPT = PromptTemplate.from_template("""
아래는 부산 사하구청 행정 정보 텍스트입니다.
이 텍스트를 분석하여 JSON 형식으로 메타데이터를 추출해주세요.

텍스트:
{content}

다음 형식으로만 응답하세요 (JSON만, 설명 없이):
{{
  "service_type": "민원|복지|세금|교통|환경|교육|문화|기타" 중 하나,
  "target_audience": ["전체시민", "노인", "장애인", "아동", "청년", "임산부", "저소득층"] 중 해당하는 것들,
  "keywords": 핵심 키워드 5개 이내의 리스트,
  "has_deadline": true 또는 false,
  "has_contact_info": true 또는 false,
  "summary": 한 줄 요약 (50자 이내)
}}
""")


class MetadataTagger:
    def __init__(self):
        if not GROQ_API_KEY:
            logger.warning("GROQ_API_KEY 미설정 - 메타데이터 태깅 비활성화")
            self.llm = None
            return
        try:
            self.llm = ChatGroq(
                model=GROQ_LLM_MODEL,
                api_key=GROQ_API_KEY,
                temperature=0,
            )
            self.chain = TAGGING_PROMPT | self.llm
            logger.info(f"Groq 연결 완료: {GROQ_LLM_MODEL}")
        except Exception as e:
            logger.warning(f"Groq 초기화 실패 - 태깅 비활성화: {e}")
            self.llm = None

    def tag(self, chunk) -> dict:
        """청크에 메타데이터 태그 추가"""
        base_meta = {
            "url": chunk.url,
            "title": chunk.title,
            "category": chunk.category,
            "sub_category": chunk.sub_category,
            "chunk_index": chunk.chunk_index,
            "total_chunks": chunk.total_chunks,
        }

        if not self.llm:
            return base_meta

        try:
            response = self.chain.invoke({"content": chunk.content[:800]})
            text = response.content.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                llm_meta = json.loads(text[start:end])
                base_meta.update(llm_meta)
        except Exception as e:
            logger.warning(f"태깅 실패 ({chunk.chunk_id}): {e}")

        return base_meta

    def tag_batch(self, chunks: list, batch_size: int = 10) -> list[tuple]:
        """배치 태깅 (무료 티어: 분당 15회 제한 → 5초 간격)"""
        results = []
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            for chunk in batch:
                meta = self.tag(chunk)
                results.append((chunk, meta))
                time.sleep(25)  # 분당 2~3회로 보수적 대응 (무료 할당량 보존)
            logger.info(f"태깅 진행: {min(i+batch_size, len(chunks))}/{len(chunks)}")
        return results
