"""
하이브리드 검색 모듈
- 1차 필터링: 메타데이터(카테고리, 서비스 유형) 기반 범위 축소
- 2차 의미 검색: 벡터 유사도 (pgvector match_documents RPC)
- 3차 키워드 보강: BM25 점수와 가중 합산하여 최종 랭킹
"""

import logging
from database_db.vector_store import VectorStore
from database_db.database import Database
from chatbot.dept_directory import correct_dept, get_contact, search_staff_directory
from config import (
    HYBRID_VECTOR_WEIGHT,
    HYBRID_BM25_WEIGHT,
    HYBRID_BM25_TOP_N,
)

logger = logging.getLogger(__name__)


def _normalize_scores(scored_items: list[tuple[str, float]]) -> dict[str, float]:
    """min-max 정규화로 점수를 [0, 1] 범위로 변환"""
    if not scored_items:
        return {}
    scores = [s for _, s in scored_items]
    smin, smax = min(scores), max(scores)
    if smax - smin < 1e-9:
        return {doc_id: 1.0 for doc_id, _ in scored_items}
    return {
        doc_id: (s - smin) / (smax - smin)
        for doc_id, s in scored_items
    }


class HybridRetriever:
    def __init__(self):
        self.vs = VectorStore()
        self.db = Database()

        # BM25 인덱스 사전 로딩 (지연 로딩하면 첫 질문 시 수 초 지연)
        try:
            from chatbot.bm25_index import BM25Index
            self.bm25 = BM25Index()
        except Exception as e:
            logger.warning(f"BM25 인덱스 사전 로딩 실패: {e}")
            self.bm25 = None

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

    def _hybrid_combine(self, query: str, vector_results: list[dict], k: int) -> list[dict]:
        """
        벡터 결과와 BM25 점수를 가중 합산하여 재랭킹.
        BM25 비활성화 또는 미설치 시 벡터 결과 그대로 반환.
        """
        if not self.bm25 or not self.bm25.enabled:
            return vector_results[:k]

        # BM25 후보 집합
        bm25_results = self.bm25.search(query, top_n=HYBRID_BM25_TOP_N)
        if not bm25_results:
            return vector_results[:k]

        # 두 결과의 union으로 후보 풀 구성
        candidates: dict[str, dict] = {}
        for r in vector_results:
            candidates[r["id"]] = {**r, "bm25_score": 0.0}
        for r in bm25_results:
            if r["id"] in candidates:
                candidates[r["id"]]["bm25_score"] = r["bm25_score"]
            else:
                candidates[r["id"]] = {
                    "id": r["id"],
                    "content": r["content"],
                    "metadata": r["metadata"],
                    "similarity": 0.0,
                    "bm25_score": r["bm25_score"],
                }

        # 점수 정규화
        vec_norm = _normalize_scores([(cid, c["similarity"]) for cid, c in candidates.items()])
        bm25_norm = _normalize_scores([(cid, c["bm25_score"]) for cid, c in candidates.items()])

        # 가중 합산
        for cid, c in candidates.items():
            c["hybrid_score"] = (
                HYBRID_VECTOR_WEIGHT * vec_norm.get(cid, 0)
                + HYBRID_BM25_WEIGHT * bm25_norm.get(cid, 0)
            )

        # 정렬 후 상위 k개
        ranked = sorted(candidates.values(), key=lambda x: x["hybrid_score"], reverse=True)[:k]
        for d in ranked:
            title = (d["metadata"].get("title") or "?")[:30]
            logger.info(
                f"  [하이브리드] hybrid={d['hybrid_score']:.3f} "
                f"(vec={d.get('similarity', 0):.2f}/bm25={d['bm25_score']:.2f}) | {title}"
            )

        # 출처 표시는 similarity 키를 사용하므로 hybrid_score로 갱신
        for d in ranked:
            d["similarity"] = d["hybrid_score"]
        return ranked

    def _staff_results_to_documents(self, query: str, limit: int = 5) -> list[dict]:
        official_hits = search_staff_directory(query, limit=limit)
        if not official_hits:
            return []

        top_score = max(hit.get("score", 0.0) for hit in official_hits) or 1.0
        docs: list[dict] = []
        for idx, hit in enumerate(official_hits, 1):
            dept = correct_dept(hit.get("department", "") or "")
            phone = (hit.get("contact", "") or "").strip() or get_contact(dept)
            duties = (hit.get("duties", "") or "").strip()
            title = (hit.get("title", "") or dept or "직원업무안내").strip()
            content_lines = []
            if dept:
                content_lines.append(f"공식 담당부서: {dept}")
            if title:
                content_lines.append(f"직위: {title}")
            if phone:
                content_lines.append(f"공식 전화번호: {phone}")
            if duties:
                content_lines.append(f"업무: {duties}")
            docs.append(
                {
                    "id": f"staff:{dept}:{title}:{idx}",
                    "content": "\n".join(content_lines) or duties or f"{dept} {title}".strip(),
                    "metadata": {
                        "url": hit.get("url", "") or "https://www.saha.go.kr/portal/staff/list.do?mId=0604030000",
                        "title": title,
                        "category": "staff_directory",
                        "service_type": "기타",
                        "department": dept,
                        "contact": phone,
                    },
                    "similarity": min(1.0, float(hit.get("score", 0.0)) / top_score),
                }
            )
        return docs

    def _resolve_official_source(self, query: str, title: str, content: str, dept: str) -> tuple[str, str]:
        lookup_text = " ".join(part for part in [query, title, content, dept] if part)
        hits = search_staff_directory(lookup_text, limit=1)
        if hits:
            hit = hits[0]
            resolved_dept = correct_dept(hit.get("department", "") or dept or "")
            resolved_contact = (hit.get("contact", "") or "").strip() or get_contact(resolved_dept)
            return resolved_dept, resolved_contact

        resolved_dept = correct_dept(dept) if dept else ""
        return resolved_dept, (get_contact(resolved_dept) if resolved_dept else "")

    def search(self, query: str, k: int = 5) -> dict:
        """
        하이브리드 검색 수행
        1. 질문에서 메타데이터 힌트 감지
        2. 감지된 필터로 벡터 검색
        3. 결과 부족 시 필터 해제하여 전체 벡터 검색
        4. BM25 점수와 가중 합산하여 재랭킹

        Returns:
            {
                "results": list[dict],   # 검색된 문서 목록
                "degraded": bool,        # 검색 파이프라인 부분 실패 여부
                "reason": str | None,    # degraded=True일 때 원인 코드
            }

        degraded=True 케이스:
            - vector_search_failed: 벡터 RPC 호출 자체가 예외로 실패
            - bm25_failed: BM25 인덱스가 비활성 상태라 키워드 보정 불가
              (벡터 결과만으로 응답하므로 정확도가 평소보다 낮을 수 있음)
        """
        hints = self.detect_category(query)
        logger.info(f"검색 힌트: {hints}")

        degraded = False
        reason: str | None = None

        try:
            # 1차: 메타데이터 필터 + 벡터 검색 (k의 2배를 가져와 재랭킹 여유 확보)
            results = self.vs.hybrid_search(
                query=query,
                category=hints.get("category"),
                service_type=hints.get("service_type"),
                k=k * 2,
            )

            # 결과 부족 시 필터 해제
            if len(results) < 2:
                logger.info("필터 결과 부족 → 전체 범위 검색")
                results = self.vs.similarity_search(query, k=k * 2)
        except Exception as e:
            logger.warning(f"벡터 검색 실패: {e}")
            return {"results": [], "degraded": True, "reason": "vector_search_failed"}

        official_docs = self._staff_results_to_documents(query, limit=max(k, 3))
        if official_docs:
            results = official_docs + results

        # BM25 비활성 상태이면 벡터 결과만 사용하면서 degraded 표시
        if not self.bm25 or not self.bm25.enabled:
            degraded = True
            reason = "bm25_failed"
            return {"results": results[:k], "degraded": degraded, "reason": reason}

        # BM25 결합 재랭킹
        combined = self._hybrid_combine(query, results, k=k)
        return {"results": combined, "degraded": degraded, "reason": reason}

    def _is_relevant_source(self, query: str, title: str, content: str) -> bool:
        """질문 키워드가 문서 제목이나 내용에 실제로 포함되어 있는지 확인"""
        stopwords = {"알려줘", "알려주세요", "뭐야", "어떻게", "해줘", "있어", "없어",
                     "하고", "싶어", "인가요", "인지", "대해", "관련", "안내", "정보",
                     "사하구", "사하구청", "부산"}

        query_keywords = set()
        for word in query.replace("?", "").replace(".", "").split():
            word = word.strip()
            if len(word) >= 2 and word not in stopwords:
                query_keywords.add(word)

        if not query_keywords:
            return True

        combined = title + " " + content
        return any(kw in combined for kw in query_keywords)

    def format_context(self, query: str, results: list[dict]) -> tuple[str, list[dict]]:
        """검색 결과를 LLM 컨텍스트 + 출처 목록으로 변환"""
        if not results:
            return "", []

        context_parts = []
        relevant_sources = []   # 질문 키워드가 실제로 포함된 출처 (우선 제시)
        fallback_sources = []   # 그 외 상위 결과 (관련 출처가 하나도 없을 때 폴백)
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
                f"담당부서: {meta.get('department', '')}\n"
                f"연락처: {meta.get('contact', '')}\n"
                f"내용: {content}\n"
            )

            if url and url not in seen_urls:
                seen_urls.add(url)
                # 담당 부서 (LLM이 본문에서 추출) → 공식 명칭으로 보정 후 연락처 매핑
                dept = correct_dept(meta.get("department", "") or "")
                dept, contact = self._resolve_official_source(query, title, content, dept)
                src = {
                    "title": title,
                    "url": url,
                    "category": meta.get("category", ""),
                    "service_type": meta.get("service_type", "기타"),
                    "department": dept,
                    # 담당부서 연락처 (확인된 직통번호 없으면 대표전화로 폴백)
                    "contact": (meta.get("contact") or "").strip() or contact,
                }
                if self._is_relevant_source(query, title, content):
                    relevant_sources.append(src)
                else:
                    fallback_sources.append(src)

        # 출처는 반드시 함께 제시: 관련성 통과분이 있으면 그것을, 없으면 상위 결과로 폴백.
        sources = relevant_sources if relevant_sources else fallback_sources[:3]

        context = "\n---\n".join(context_parts)
        return context, sources
