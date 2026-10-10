"""
하이브리드 검색 모듈
- 1차 필터링: 메타데이터(카테고리, 서비스 유형) 기반 범위 축소
- 2차 의미 검색: 벡터 유사도 (pgvector match_documents RPC)
- 3차 키워드 보강: BM25 점수와 가중 합산하여 최종 랭킹
"""

import re
import logging
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from database_db.vector_store import VectorStore
from database_db.database import Database
from chatbot.dept_directory import (
    correct_dept, get_contact, search_staff_directory, is_staff_lookup, staff_subject_terms,
)
from chatbot.evidence import (
    assess_evidence as evaluate_evidence,
    is_official_document,
    select_grounded_results as filter_grounded_results,
    filter_time_compatible,
    is_answerable_document,
    topic_support,
    is_service_source,
)
from chatbot.query_subject import normalize_query, subject_query, query_keywords, fallback_keywords
from chatbot.crawled_pages import CrawledPageIndex, page_rank
from chatbot.question_intent import asks_opening_hours, asks_location
from chatbot.faq_targets import find_official_question, match_official_page
from config import (
    HYBRID_VECTOR_WEIGHT,
    HYBRID_BM25_WEIGHT,
    HYBRID_BM25_TOP_N,
    BM25_FAST_PATH_MIN_SCORE,
    CONFIDENCE_MIN_SIMILARITY,
    SOURCE_MAX_AGE_DAYS,
    SOURCE_DYNAMIC_MAX_AGE_DAYS,
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
        self.page_index = CrawledPageIndex(self.db.client)

        # BM25 인덱스 사전 로딩 (지연 로딩하면 첫 질문 시 수 초 지연)
        try:
            from chatbot.bm25_index import BM25Index
            self.bm25 = BM25Index()
        except Exception as e:
            logger.warning(f"BM25 인덱스 사전 로딩 실패: {e}")
            self.bm25 = None
        self.page_index._snapshot()

    @staticmethod
    def find_official_question(query: str) -> dict | None:
        return find_official_question(query)

    @classmethod
    def _has_staff_lookup_intent(cls, query: str) -> bool:
        from chatbot.contact_directory import is_contact_lookup_question
        return is_staff_lookup(query) or is_contact_lookup_question(query)

    @staticmethod
    def _is_staff_document(doc: dict) -> bool:
        meta = doc.get('metadata') or {}
        return meta.get('category') == 'staff_directory' or 'staff/list.do' in str(meta.get('url', ''))

    def detect_category(self, query: str) -> dict:
        """질문에서 카테고리/서비스유형 힌트 감지"""
        category_keywords = {
            "정보공개": ["정보공개", "공시", "예산", "결산", "감사"],
            "사하복지": ["복지", "지원", "수당", "돌봄", "보육", "장애", "노인", "어르신", "아동"],
            "전자민원": ["민원", "신청", "발급", "증명", "신고", "등록", "허가"],
            "분야별정보": ["분야별정보", "시정", "행정"],
            "구민참여": ["참여", "제안", "청원", "설문", "공모"],
            "사하소개": ["사하구", "구청장", "조직", "연혁", "위치", "오시는"],
        }
        service_keywords = {
            "통계": ["통계", "분석", "방문자", "검색어", "청구건수"],
            "민원": ["민원", "신청", "발급", "증명서", "등본", "초본"],
            "복지": ["복지", "지원금", "수당", "바우처", "돌봄"],
            "세금": ["세금", "납부", "세무", "지방세", "재산세", "자동차세"],
            "교통": ["교통", "버스", "주차", "도로", "지하철"],
            "환경": ["환경", "쓰레기", "재활용", "분리수거", "청소"],
            "교육": ["교육", "학교", "평생학습", "강좌", "수강"],
            "문화": ["문화", "축제", "공연", "체육", "도서관"],
            "보건": ["보건", "건강", "진료", "접종", "검진", "임산부", "치매"],
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

    def search_official_url(self, query: str, url: str, k: int = 15) -> dict:
        """Search the live page named by a verified workbook question."""
        # A validated complete original already contains the conditions that
        # chunks could omit. A known URL needs neither a global BM25 search
        # nor loading every crawler page.
        pages = self.search_crawled_pages(query, k=k, url=url)
        if pages:
            return {"results": pages, "degraded": False, "reason": None}
        try:
            rows = self.db.client.table("documents").select("id,content,metadata").eq(
                "metadata->>url", url
            ).execute().data or []
        except Exception as exc:
            logger.warning("질문 목록 공식 URL 검색 실패")
            return {"results": pages, "degraded": True, "reason": "faq_source_failed"}
        keywords = self._content_keywords(query)
        bm25_scores = {}
        if self.bm25 and self.bm25.enabled:
            bm25_scores = {row["id"]: row["bm25_score"] for row in self.bm25.search(query, top_n=100)}
        ranked = []
        for row in rows:
            meta = row.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except ValueError:
                    meta = {}
            content = row.get("content") or ""
            overlap = sum(keyword in f"{meta.get('title', '')} {content}" for keyword in keywords)
            ranked.append({
                "id": row["id"], "content": content, "metadata": meta,
                "similarity": 0.0, "vector_similarity": 0.0,
                "bm25_score": max(1.0, float(bm25_scores.get(row["id"], 0.0))),
                "_overlap": overlap,
            })
        ranked.sort(key=lambda doc: (doc["_overlap"], doc["bm25_score"]), reverse=True)
        for doc in ranked:
            doc.pop("_overlap", None)
        return {"results": pages + ranked[:k], "degraded": False, "reason": None}

    def search_crawled_pages(self, query: str, k: int = 15, url: str | None = None) -> list[dict]:
        index = getattr(self, "page_index", None)
        return index.search(query, self._content_keywords(query), limit=k, url=url) if index else []

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
        # vector_similarity: 하이브리드 정규화 전 "원본 코사인 유사도"를 보존한다.
        #   (hybrid_score는 후보 풀 내 min-max 정규화라 최상위가 항상 ~1.0이 되어
        #    절대적 신뢰도 지표로 쓸 수 없으므로, 신뢰도 게이트는 이 값을 사용)
        candidates: dict[str, dict] = {}
        for r in vector_results:
            candidates[r["id"]] = {**r, "bm25_score": 0.0, "vector_similarity": r.get("similarity", 0.0)}
        for r in bm25_results:
            if r["id"] in candidates:
                candidates[r["id"]]["bm25_score"] = r["bm25_score"]
            else:
                candidates[r["id"]] = {
                    "id": r["id"],
                    "content": r["content"],
                    "metadata": r["metadata"],
                    "similarity": 0.0,
                    "vector_similarity": 0.0,
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
                        "source_type": "staff_directory",
                    },
                    "similarity": min(1.0, float(hit.get("score", 0.0)) / top_score),
                    "bm25_score": float(hit.get("score", 0.0)),
                }
            )
        return docs

    def _resolve_official_source(self, query: str, title: str, content: str, dept: str) -> tuple[str, str]:
        resolved_dept = correct_dept(dept) if dept else ""
        if resolved_dept:
            return resolved_dept, get_contact(resolved_dept)

        # 직원·연락처를 직접 묻는 질문에서만 직원업무안내를 이용해 부서를
        # 추론한다. 일반 정보 질문에서는 비슷한 업무명만으로 부서를 붙이지 않는다.
        if any(word in (query or "") for word in self._CONTACT_INTENT):
            lookup_text = " ".join(part for part in [query, title, content] if part)
            hits = search_staff_directory(lookup_text, limit=1)
            if hits:
                hit = hits[0]
                resolved_dept = correct_dept(hit.get("department", "") or "")
                resolved_contact = (hit.get("contact", "") or "").strip() or get_contact(resolved_dept)
                return resolved_dept, resolved_contact

        return "", ""

    # 인물/연락처 의도 표현 (이때만 직원업무안내 문서를 상위에 노출)
    _CONTACT_INTENT = (
        "담당", "부서", "연락처", "전화", "번호", "문의", "누구", "과장",
        "팀장", "계장", "주무관", "청장", "직원", "담당자", "소장", "과는",
    )

    # 행정 상담 도메인임을 명확히 드러내는 표현. 벡터 유사도만 높은 도메인 밖
    # 질문이 신뢰도 게이트를 통과하지 않도록 보조 신호로 사용한다.
    _DOMAIN_INTENT = (
        "사하", "구청", "민원", "신청", "발급", "신고", "복지", "지원",
        "수당", "세금", "납부", "주차", "도로", "교통", "쓰레기", "폐기물",
        "재활용", "청소", "보육", "교육", "도서관", "축제", "체육", "부서",
        "담당", "공무원", "행정", "주민", "전입", "등본", "증명서",
    )

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
        query = normalize_query(query)
        hints = self.detect_category(query)
        logger.info(f"검색 힌트: {hints}")

        # Responsibility questions require a matching duty/role. Re-ranking
        # with generic board columns such as '담당부서' must not replace them.
        if is_staff_lookup(query):
            staff_docs = self._staff_results_to_documents(query, limit=k)
            return {"results": staff_docs, "degraded": not bool(staff_docs),
                    "reason": None if staff_docs else "staff_not_found"}

        # Resolve the team's FAQ aliases to current crawler originals. Draft
        # answers and manually entered verification dates are not evidence.
        target = match_official_page(query)
        if target:
            pages = self.search_crawled_pages(query, k=k, url=target)
            if pages:
                return {"results": pages, "degraded": False, "reason": None}

        # The original contains fields and qualifications that embedding
        # chunks can omit. Search every crawler page, not just workbook URLs.
        pages = self.search_crawled_pages(query, k=k)
        if pages:
            lexical = self.bm25.search(query, top_n=max(k, 30)) if self.bm25 and self.bm25.enabled else []
            subjects = self._content_keywords(query)
            return {"results": sorted(pages + lexical,
                key=lambda doc: page_rank(query, doc, subjects), reverse=True),
                "degraded": False, "reason": None}

        degraded = False
        reason: str | None = None

        # 행정 용어·품목명이 정확히 일치하는 질문은 CPU 벡터 임베딩(수십 초)을
        # 기다리지 않고 BM25 결과를 사용한다. 점수가 약한 자연어 질문은 아래의
        # 벡터+BM25 하이브리드 경로를 그대로 탄다.
        contact_intent = self._has_staff_lookup_intent(query)
        if self.bm25 and self.bm25.enabled and not contact_intent:
            lexical_results = self.bm25.search(query, top_n=max(k, 10))
            subjects = self._content_keywords(query)
            lexical_results = [row for row in lexical_results if topic_support(row, subjects)[0]]
            lexical_results = [row for row in lexical_results if not self._is_staff_document(row)]
            if (
                lexical_results
                and lexical_results[0]["bm25_score"] >= BM25_FAST_PATH_MIN_SCORE
                and self._is_official_document(lexical_results[0])
            ):
                top_score = lexical_results[0]["bm25_score"] or 1.0
                fast_results = []
                for row in lexical_results[:k]:
                    fast_results.append({
                        **row,
                        "similarity": min(1.0, row["bm25_score"] / top_score),
                        "vector_similarity": 0.0,
                        "hybrid_score": min(1.0, row["bm25_score"] / top_score),
                    })
                logger.info(
                    f"BM25 고신뢰 빠른 경로: score={top_score:.2f}, "
                    f"results={len(fast_results)}"
                )
                return {"results": fast_results, "degraded": False, "reason": None}

        try:
            # 메타데이터 필터는 "단일 facet"만 사용한다.
            #   과거: category(예: 사하소개) AND service_type(예: 교통)를 동시에 걸면
            #   필터가 과도하게 좁아져, "사하구 도로명주소 안내도" 같은 질문에서 정작
            #   관련 페이지가 통째로 누락됐다(둘 다 만족하는 청크가 거의 없음).
            #   → 더 구체적인 service_type을 우선 쓰고, 없으면 category만 사용.
            single_category = None
            single_service = None
            if hints.get("service_type"):
                single_service = hints["service_type"]
            elif hints.get("category"):
                single_category = hints["category"]

            results = self.vs.hybrid_search(
                query=query,
                category=single_category,
                service_type=single_service,
                k=k * 2,
            )

            # 필터 결과가 부족하면 필터 해제하여 전체 의미검색으로 대체 (baseline과 동일)
            if len(results) < 2:
                logger.info("필터 결과 부족 → 전체 범위 검색")
                results = self.vs.similarity_search(query, k=k * 2)
        except Exception as e:
            logger.warning(f"벡터 검색 실패: {e}")
            return {"results": [], "degraded": True, "reason": "vector_search_failed"}

        # 직원업무안내(staff) 문서는 "담당/연락처/부서/직원" 등 인물·연락 의도가 있는
        # 질문에서만 상위에 끼워 넣는다. 그렇지 않으면 staff가 "사하구청장"처럼 지명만으로
        # 매칭돼 콘텐츠 페이지(예: 안내도·자료)를 밀어내므로 제외한다.
        if contact_intent:
            official_docs = self._staff_results_to_documents(query, limit=max(k, 3))
            if official_docs:
                results = official_docs + results
        else:
            results = [doc for doc in results if not self._is_staff_document(doc)]

        # BM25 비활성 상태이면 벡터 결과만 사용하면서 degraded 표시
        if not self.bm25 or not self.bm25.enabled:
            degraded = True
            reason = "bm25_failed"
            return {"results": results[:k], "degraded": degraded, "reason": reason}

        # BM25 결합 재랭킹
        combined = self._hybrid_combine(query, results, k=k)
        return {"results": combined, "degraded": degraded, "reason": reason}

    @staticmethod
    def _is_official_document(doc: dict) -> bool:
        """사하구 공식 웹 문서 또는 관리자가 적재한 내부 파일인지 확인한다."""
        return is_official_document(doc)

    def assess_evidence(self, query: str, results: list[dict]) -> dict:
        """질문의 핵심 업무를 뒷받침하는 개별 공식 문서가 있는지 평가한다.

        지역명과 '신고/신청/방법' 같은 공통 표현은 근거 판정에서 제외한다.
        벡터 유사도나 BM25 점수만으로 다른 업무의 문서를 통과시키지 않는다.

        반환되는 상태값은 사용자에게 백분율 대신 '공식 자료 확인됨/추가 확인 필요'처럼
        근거의 성격을 설명하는 데 사용한다.
        """
        keywords = self._content_keywords(query)
        query_lower = query.lower()
        domain_intent = bool(self.detect_category(query)) or any(
            word in query_lower for word in self._DOMAIN_INTENT + self._CONTACT_INTENT
        )
        return evaluate_evidence(
            [doc for doc in filter_time_compatible(query, results) if is_answerable_document(query, doc) and is_service_source(query, doc, keywords)],
            keywords=keywords,
            domain_intent=domain_intent,
            min_similarity=CONFIDENCE_MIN_SIMILARITY,
        )

    def assess_confidence(self, query: str, results: list[dict]) -> tuple[bool, float]:
        """기존 호출부와 평가 스크립트를 위한 하위 호환 래퍼."""
        evidence = self.assess_evidence(query, results)
        return evidence["confident"], evidence["top_similarity"]

    def select_grounded_results(self, query: str, results: list[dict], limit: int = 5) -> list[dict]:
        """질문 핵심 업무와 일치하는 공식 문서만 답변에 전달한다."""
        keywords = self._content_keywords(query)
        domain_intent = bool(self.detect_category(query)) or any(
            word in query.lower() for word in self._DOMAIN_INTENT + self._CONTACT_INTENT
        )
        return filter_grounded_results(
            [doc for doc in filter_time_compatible(query, results) if is_answerable_document(query, doc) and is_service_source(query, doc, keywords)],
            keywords=keywords,
            domain_intent=domain_intent,
            min_similarity=CONFIDENCE_MIN_SIMILARITY,
            limit=limit,
        )

    def filter_fresh_results(self, query: str, results: list[dict]) -> list[dict]:
        """Only use web evidence checked recently; historical reports remain dated evidence."""
        results = filter_time_compatible(query, results)
        urls = [str((doc.get("metadata") or {}).get("url") or "") for doc in results
                if (doc.get("metadata") or {}).get("source_type") != "official_report"
                and (doc.get("metadata") or {}).get("category") != "staff_directory"]
        originals = {}
        if urls:
            try:
                rows = self.db.client.table("raw_pages").select(
                    "url,last_checked_at,content,attachments"
                ).in_("url", list(set(urls))).execute().data or []
                originals = {row["url"]: row for row in rows}
            except Exception as exc:
                logger.warning("출처 확인 시각 조회 실패: %s", exc)
        dynamic = asks_opening_hours(query) or asks_location(query) or any(word in (query or "") for word in (
            "현재", "지금", "올해", "오늘", "최신", "운영", "시간", "수수료",
            "비용", "금액", "요금", "지원금", "기준", "대상", "기간", "언제",
            "전화", "연락처", "담당", "주소", "위치", "얼마", "몇 시",
        ))
        age_days = SOURCE_DYNAMIC_MAX_AGE_DAYS if dynamic else SOURCE_MAX_AGE_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=age_days)
        kept = []
        for doc in results:
            meta = doc.get("metadata") or {}
            if meta.get("source_type") == "official_report":
                kept.append(doc)
                continue
            if meta.get("category") == "staff_directory":
                try:
                    from crawler.staff_directory import OUTPUT_PATH
                    data = json.loads(Path(OUTPUT_PATH).read_text(encoding="utf-8"))
                    date_value = data.get("generated_at")
                except Exception:
                    date_value = None
            else:
                date_value = originals.get(meta.get("url"), {}).get('last_checked_at')
            try:
                verified = datetime.fromisoformat(str(date_value).replace("Z", "+00:00"))
                if verified.tzinfo is None:
                    verified = verified.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            if verified >= cutoff:
                doc = {**doc, "metadata": {**meta, "checked_at": verified.date().isoformat()}}
                if meta.get('category') != 'staff_directory':
                    original = originals[meta.get('url')]
                    doc['_raw_page'] = original
                    if meta.get('source_type') == 'crawled_page':
                        # Refresh the candidate's full body too. A worker may
                        # change it while the background index still holds
                        # an older snapshot with a recent check timestamp.
                        from chatbot.source_answers import strip_page_chrome
                        doc['content'] = strip_page_chrome(original.get('content') or '')
                        doc['metadata']['attachments'] = original.get('attachments') or []
                kept.append(doc)
        return kept

    # 신뢰도 판정용 불용어 (출처 표시용 _is_relevant_source와 별도 유지)
    _CONF_STOPWORDS = {
        "알려줘", "알려주세요", "뭐야", "어떻게", "해줘", "있어", "없어", "하고",
        "싶어", "인가요", "인지", "대해", "관련", "안내", "정보", "사하구", "사하구청",
        "부산", "얼마야", "얼마", "무엇", "어디", "언제", "누구",
    }

    # 어말 1글자 조사 (어간 추출용) — 명사 뒤에 붙어 키워드 매칭을 방해함
    _JOSA = ("을", "를", "이", "가", "은", "는", "와", "과", "의", "에", "도", "로", "만")

    def _strip_josa(self, word: str) -> str:
        """'위치와'→'위치', '가격이'→'가격'처럼 어말 조사 1글자 제거 (어간 ≥2자 유지)."""
        if len(word) >= 3 and word[-1] in self._JOSA:
            return word[:-1]
        return word

    def _content_keywords(self, query: str) -> set[str]:
        """질문에서 의미 있는 내용어만 추출 (순수 숫자·불용어·짧은 토큰 제외, 조사 제거)."""
        if is_staff_lookup(query):
            return staff_subject_terms(query)
        text = subject_query(query)
        kiwi = getattr(getattr(self, "bm25", None), "kiwi", None)
        if kiwi is not None:
            words = [token.form for token in kiwi.tokenize(text)
                     if token.tag.startswith(("NN", "SL"))]
            return query_keywords(query, words)
        return fallback_keywords(text)

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
        sources = []
        seen_urls = set()

        for i, doc in enumerate(results, 1):
            if self._is_staff_document(doc) and not self._has_staff_lookup_intent(query):
                continue
            meta = doc.get("metadata", {})
            url = meta.get("url", "")
            title = meta.get("title", "정보")
            content = doc.get("content", "")
            is_report = meta.get("source_type") == "official_report"
            provenance = (
                f"보고서 작성일: {meta.get('issued_at', '')}; 자료 기준 기간: {meta.get('data_period', '')}; "
                f"쪽: {meta.get('page_number', '')}"
                if is_report else f"홈페이지 확인일: {meta.get('checked_at', '')}"
            )

            context_parts.append(
                f"[참고자료 {i}]\n"
                f"제목: {title}\n"
                f"출처 구분: {'사하구 공식 분석 보고서 (과거 통계)' if is_report else '사하구 홈페이지'}\n"
                f"{provenance}\n"
                f"담당부서: {meta.get('department', '')}\n"
                f"연락처: {meta.get('contact', '')}\n"
                f"내용: {content}\n"
            )

            if url and url not in seen_urls:
                seen_urls.add(url)
                # 담당 부서 (LLM이 본문에서 추출) → 공식 명칭으로 보정 후 연락처 매핑
                is_faq = meta.get('category') == 'official_faq'
                dept = "" if is_report or is_faq else correct_dept(meta.get("department", "") or "")
                dept, contact = ("", "") if is_report or is_faq else self._resolve_official_source(query, title, content, dept)
                # 첨부파일 목록 정규화 ([{"name","url"}]만 통과)
                # documents.metadata는 환경에 따라 list 또는 JSON 문자열로 올 수 있어
                # 문자열이면 파싱한다 (파싱 실패 시 빈 목록 — 첨부를 조용히 버리지 않도록).
                raw_attachments = meta.get("attachments") or []
                if isinstance(raw_attachments, str):
                    try:
                        import json as _json
                        raw_attachments = _json.loads(raw_attachments)
                    except Exception:
                        raw_attachments = []
                if not isinstance(raw_attachments, list):
                    raw_attachments = []
                attachments = [
                    {"name": str(a.get("name") or a.get("title") or "첨부파일"), "url": str(a.get("url", ""))}
                    for a in raw_attachments
                    if isinstance(a, dict) and a.get("url")
                ]
                src = {
                    "title": title,
                    "url": "" if is_report else url,
                    "category": meta.get("category", ""),
                    "service_type": "과거 통계" if is_report else meta.get("service_type", "기타"),
                    "department": dept,
                    # 담당부서 연락처 (확인된 직통번호 없으면 대표전화로 폴백)
                    "contact": "" if is_report else (meta.get("contact") or "").strip() or contact,
                    "attachments": attachments,
                    "source_type": meta.get("source_type", "official_page"),
                    "issued_at": meta.get("issued_at", ""),
                    "data_period": meta.get("data_period", ""),
                    "page_number": int(meta.get("page_number") or 0),
                    "checked_at": meta.get("checked_at", ""),
                }
                sources.append(src)

        context = "\n---\n".join(context_parts)
        return context, sources[:5]
