"""
하이브리드 검색 모듈
1차 필터링: 메타데이터(카테고리, 서비스유형) 기반 범위 축소
2차 정밀 검색: 벡터 유사도 검색
"""

import json
import logging
from database_db.vector_store import VectorStore
from database_db.database import Database

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(self):
        self.vs = VectorStore()
        self.db = Database()

    def detect_category(self, query: str) -> dict:
        """질문에서 카테고리/서비스유형 힌트 감지"""
        category_keywords = {
            "분야별정보": ["분야", "정보", "시정", "행정"],
            "사하복지": ["복지", "지원", "수당", "돌봄", "보육", "장애", "노인", "어르신", "아동"],
            "전자민원": ["민원", "신청", "발급", "증명", "신고", "등록", "허가"],
            "정보공개": ["정보공개", "공시", "예산", "결산", "감사"],
            "구민참여": ["참여", "제안", "청원", "설문", "공모"],
            "사하소개": ["사하구", "구청장", "조직", "연혁", "위치", "오시는"],
        }
        service_keywords = {
            "민원": ["민원", "신청", "발급", "증명서", "등본", "초본"],
            "복지": ["복지", "지원금", "수당", "바우처", "돌봄"],
            "세금": ["세금", "납부", "세무", "지방세", "재산세", "자동차세"],
            "교통": ["교통", "버스", "주차", "도로", "지하철"],
            "환경": ["환경", "쓰레기", "재활용", "분리수거", "청소"],
            "교육": ["교육", "학교", "평생학습", "강좌", "수강"],
            "문화": ["문화", "축제", "공연", "체육", "도서관"],
        }

        detected = {}
        query_lower = query.lower()

        for cat, keywords in category_keywords.items():
            if any(kw in query_lower for kw in keywords):
                detected["category"] = cat
                break

        for svc, keywords in service_keywords.items():
            if any(kw in query_lower for kw in keywords):
                detected["service_type"] = svc
                break

        return detected

    def search(self, query: str, k: int = 5) -> list[dict]:
        """
        하이브리드 검색 수행
        1. 질문에서 메타데이터 힌트 감지
        2. 감지된 필터로 범위 축소 + 벡터 검색
        3. 필터 결과가 부족하면 전체 범위로 폴백
        """
        hints = self.detect_category(query)
        logger.info(f"검색 힌트: {hints}")

        try:
            # 1차: 메타데이터 필터 + 벡터 검색
            results = self.vs.hybrid_search(
                query=query,
                category=hints.get("category"),
                service_type=hints.get("service_type"),
                k=k,
            )

            # 결과가 부족하면 필터 없이 전체 검색
            if len(results) < 2:
                logger.info("필터 결과 부족 → 전체 범위 검색")
                results = self.vs.similarity_search(query, k=k)

            return results
        except Exception as e:
            logger.warning(f"벡터 검색 실패 (Supabase SQL 미설정?): {e}")
            return []

    def format_context(self, results: list[dict]) -> tuple[str, list[dict]]:
        """검색 결과를 LLM 컨텍스트 + 출처 목록으로 변환"""
        if not results:
            return "", []

        context_parts = []
        sources = []
        seen_urls = set()

        for i, doc in enumerate(results, 1):
            meta = doc.get("metadata", {})
            url = meta.get("url", "")
            title = meta.get("title", "정보")
            content = doc.get("content", "")
            similarity = doc.get("similarity", 0)

            context_parts.append(
                f"[참고자료 {i}] (유사도: {similarity:.2f})\n"
                f"제목: {title}\n"
                f"내용: {content}\n"
            )

            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append({
                    "title": title,
                    "url": url,
                    "category": meta.get("category", ""),
                    "service_type": meta.get("service_type", "기타"),
                })

        context = "\n---\n".join(context_parts)
        return context, sources
