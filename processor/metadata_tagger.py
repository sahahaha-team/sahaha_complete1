"""
LLM 기반 메타데이터 자동 태깅 (Groq - 무료 티어)
- 청크 다중 묶음을 1회 LLM 호출로 일괄 태깅 (배치 처리)
- 단일 호출 폴백 + JSON 파싱 실패 시 단건 재시도
"""

import json
import time
import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate

from config import GROQ_API_KEY, GROQ_LLM_MODEL
from chatbot.dept_directory import correct_dept

logger = logging.getLogger(__name__)

BATCH_TAGGING_PROMPT = PromptTemplate.from_template("""
아래는 부산 사하구청 행정 정보 텍스트 여러 개입니다.
각 항목을 분석하여 메타데이터를 추출해주세요.

{items}

다음 형식의 JSON 배열만 반환하세요 (설명/마크다운 코드블록 금지).
배열의 i번째 원소는 위 i번째 항목에 대응해야 합니다.
[
  {{
    "service_type": "민원|복지|세금|교통|환경|교육|문화|기타" 중 하나,
    "department": 텍스트에 명시된 담당 부서명(예: "복지정책과", "민원여권과", "주민자치과"). 본문에 명시되지 않았으면 null,
    "target_audience": ["전체시민", "노인", "장애인", "아동", "청년", "임산부", "저소득층"] 중 해당하는 것들,
    "keywords": 핵심 키워드 5개 이내의 리스트,
    "has_deadline": true 또는 false,
    "has_contact_info": true 또는 false,
    "summary": 한 줄 요약 (50자 이내)
  }},
  ...
]
""")

SINGLE_TAGGING_PROMPT = PromptTemplate.from_template("""
아래는 부산 사하구청 행정 정보 텍스트입니다.
JSON으로만 응답하세요 (설명 없이).

텍스트:
{content}

형식:
{{
  "service_type": "민원|복지|세금|교통|환경|교육|문화|기타" 중 하나,
  "department": 텍스트에 명시된 담당 부서명(예: "복지정책과", "민원여권과", "주민자치과"). 본문에 명시되지 않았으면 null,
  "target_audience": ["전체시민", "노인", "장애인", "아동", "청년", "임산부", "저소득층"] 중 해당하는 것들,
  "keywords": 핵심 키워드 5개 이내의 리스트,
  "has_deadline": true 또는 false,
  "has_contact_info": true 또는 false,
  "summary": 한 줄 요약 (50자 이내)
}}
""")

# Groq 무료 티어: 분당 30회 → 배치(5청크) 호출 사이 2초 간격이면 안전
BATCH_SIZE = 5
BATCH_DELAY_SEC = 2.0
SINGLE_DELAY_SEC = 5.0


def _base_meta(chunk) -> dict:
    return {
        "url": chunk.url,
        "title": chunk.title,
        "category": chunk.category,
        "sub_category": chunk.sub_category,
        "chunk_index": chunk.chunk_index,
        "total_chunks": chunk.total_chunks,
    }


def _parse_json_block(text: str):
    """LLM 응답에서 JSON 블록만 추출하여 파싱 (앞뒤 설명 제거)"""
    text = text.strip()
    # 배열 우선 탐색
    for open_c, close_c in (("[", "]"), ("{", "}")):
        start = text.find(open_c)
        end = text.rfind(close_c) + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                continue
    return None


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
            self.batch_chain = BATCH_TAGGING_PROMPT | self.llm
            self.single_chain = SINGLE_TAGGING_PROMPT | self.llm
            logger.info(f"Groq 연결 완료: {GROQ_LLM_MODEL}")
        except Exception as e:
            logger.warning(f"Groq 초기화 실패 - 태깅 비활성화: {e}")
            self.llm = None

    def _tag_single(self, chunk) -> dict:
        """단건 태깅 (배치 실패 시 폴백)"""
        meta = _base_meta(chunk)
        if not self.llm:
            return meta
        try:
            response = self.single_chain.invoke({"content": chunk.content[:800]})
            parsed = _parse_json_block(response.content)
            if isinstance(parsed, dict):
                meta.update(parsed)
                if meta.get("department"):
                    meta["department"] = correct_dept(meta["department"])
        except Exception as e:
            logger.warning(f"단건 태깅 실패 ({chunk.chunk_id}): {e}")
        return meta

    def _tag_batch_one_call(self, batch: list) -> list[dict]:
        """배치를 1회 LLM 호출로 태깅. 실패 시 [] 반환 (호출자가 단건 폴백)"""
        if not self.llm or not batch:
            return [_base_meta(c) for c in batch]

        items_text = "\n\n".join(
            f"[항목 {i+1}]\n{c.content[:800]}" for i, c in enumerate(batch)
        )

        try:
            response = self.batch_chain.invoke({"items": items_text})
            parsed = _parse_json_block(response.content)
        except Exception as e:
            logger.warning(f"배치 태깅 호출 실패: {e}")
            return []

        if not isinstance(parsed, list) or len(parsed) != len(batch):
            logger.warning(
                f"배치 응답 형식 불일치 (기대 {len(batch)}, 실제 {len(parsed) if isinstance(parsed, list) else '?'})"
            )
            return []

        results = []
        for chunk, llm_meta in zip(batch, parsed):
            meta = _base_meta(chunk)
            if isinstance(llm_meta, dict):
                meta.update(llm_meta)
                if meta.get("department"):
                    meta["department"] = correct_dept(meta["department"])
            results.append(meta)
        return results

    def tag(self, chunk) -> dict:
        """단건 태깅 (외부 API)"""
        return self._tag_single(chunk)

    def tag_batch(self, chunks: list, batch_size: int = BATCH_SIZE) -> list[tuple]:
        """
        배치 태깅. 5청크 1회 LLM 호출로 처리하며,
        배치 실패 시 단건 폴백으로 안정성 확보.
        """
        results: list[tuple] = []
        total = len(chunks)

        for i in range(0, total, batch_size):
            batch = chunks[i:i + batch_size]
            batch_results = self._tag_batch_one_call(batch)

            if batch_results:
                results.extend(zip(batch, batch_results))
                time.sleep(BATCH_DELAY_SEC)
            else:
                # 배치 실패 → 단건 폴백
                logger.info(f"  배치 실패 - 단건 폴백 ({len(batch)}개)")
                for chunk in batch:
                    results.append((chunk, self._tag_single(chunk)))
                    time.sleep(SINGLE_DELAY_SEC)

            logger.info(f"태깅 진행: {min(i + batch_size, total)}/{total}")

        return results
