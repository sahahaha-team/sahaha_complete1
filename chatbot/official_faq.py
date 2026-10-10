"""구청 제공 예상질문을 최우선 근거로 사용하는 로컬 정답 인덱스."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path


DEFAULT_FAQ_PATH = Path(__file__).resolve().parent.parent / "resources" / "official_faq.json"
PRIORITY_SERVICE_PATH = Path(__file__).resolve().parent.parent / "resources" / "priority_services.json"

_STOPWORDS = {
    "사하구", "사하구청", "어떻게", "어디", "무엇", "뭐", "인가요", "있나요",
    "있습니까", "알려줘", "알려주세요", "확인", "관련", "대한", "에서", "으로",
}

_NORMALIZATION_ALIASES = {
    "쓰레기": "폐기물",
    "대형쓰레기": "대형폐기물",
    "보건증": "건강진단결과서",
    "지하철": "도시철도",
    "핸드폰": "휴대전화",
    "대표 번호": "대표전화",
    "대표번호": "대표전화",
    "온라인": "인터넷",
    "버리는 법": "배출방법",
    "버리는법": "배출방법",
    "어떻게 버리": "배출방법",
    "몇 시에 열": "진료시간",
    "몇시에 열": "진료시간",
    "문 여는 시간": "진료시간",
    "운영 시간": "이용시간",
}

_QUESTION_FILLERS = (
    "알려주세요", "알려줘", "궁금합니다", "궁금해요", "확인할수있나요",
    "확인할수있습니까", "받을수있나요", "할수있나요", "어떻게하나요",
    "어떻게하죠", "어디인가요", "어디에있나요", "무엇인가요", "뭐예요", "뭐야",
)

_CONCEPTS = (
    "대표전화", "대형폐기물", "폐가전", "음식물쓰레기", "생활쓰레기",
    "무인민원발급기", "여권", "공공근로", "평생학습", "진료시간",
    "예방접종", "보건증", "건강진단결과서", "공영주차장", "불법주정차",
    "기초생활", "장애인연금", "아이돌봄", "공시지가", "무료법률상담",
    "주민세", "사업소분", "종업원분",
)


def normalize_question(text: str) -> str:
    value = (text or "").lower()
    for source, target in _NORMALIZATION_ALIASES.items():
        value = value.replace(source, target)
    value = re.sub(r"[^0-9a-z가-힣]", "", value)
    for filler in _QUESTION_FILLERS:
        value = value.replace(filler, "")
    return value


def _tokens(text: str) -> set[str]:
    values = re.findall(r"[0-9a-z가-힣]{2,}", (text or "").lower())
    return {token for token in values if token not in _STOPWORDS and not token.isdigit()}


def _ngrams(value: str, size: int = 2) -> set[str]:
    if len(value) <= size:
        return {value} if value else set()
    return {value[i:i + size] for i in range(len(value) - size + 1)}


def _f1_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    if not overlap:
        return 0.0
    precision = overlap / len(left)
    recall = overlap / len(right)
    return 2 * precision * recall / (precision + recall)


def required_faq_ids(query: str) -> set[int]:
    """복합 질문에 반드시 함께 필요한 공식 문항을 식별한다."""
    compact = re.sub(r"[^0-9a-z가-힣]", "", (query or "").lower())
    mentions_office = any(term in compact for term in ("사하구청", "구청"))
    asks_location = any(term in compact for term in ("위치", "주소", "어디", "찾아가", "오시는길"))
    asks_contact = any(term in compact for term in ("연락처", "전화", "대표번호", "문의번호"))
    if mentions_office and asks_location and asks_contact:
        # 엑셀 공식 문항 1번(위치)과 2번(대표전화)을 모두 LLM 근거로 제공한다.
        return {1, 2}
    return set()


def question_similarity(query: str, candidate: str) -> float:
    normalized_query = normalize_question(query)
    normalized_candidate = normalize_question(candidate)
    if not normalized_query or not normalized_candidate:
        return 0.0
    if normalized_query == normalized_candidate:
        return 1.0

    query_tokens = _tokens(query)
    candidate_tokens = _tokens(candidate)
    token_score = _f1_overlap(query_tokens, candidate_tokens)
    query_concepts = {concept for concept in _CONCEPTS if concept in normalized_query}
    candidate_concepts = {concept for concept in _CONCEPTS if concept in normalized_candidate}
    # 서로 다른 행정 업무명이 명시된 문항끼리는 문장 모양이 비슷해도 매칭하지 않는다.
    # 예: 주민세 신고 질문 ↔ 기초생활수급자 수수료 면제 질문.
    if query_concepts and candidate_concepts and not (query_concepts & candidate_concepts):
        return 0.0
    if token_score == 0 and not (
        normalized_query in normalized_candidate or normalized_candidate in normalized_query
    ) and not (query_concepts & candidate_concepts):
        return 0.0

    sequence_score = SequenceMatcher(None, normalized_query, normalized_candidate).ratio()
    left_grams = _ngrams(normalized_query)
    right_grams = _ngrams(normalized_candidate)
    gram_score = len(left_grams & right_grams) / max(1, min(len(left_grams), len(right_grams)))
    containment = 1.0 if (
        normalized_query in normalized_candidate or normalized_candidate in normalized_query
    ) else 0.0
    concept_score = (
        len(query_concepts & candidate_concepts) / len(query_concepts)
        if query_concepts else 0.0
    )
    base_score = 0.30 * sequence_score + 0.25 * token_score + 0.40 * gram_score + 0.05 * containment
    if query_concepts:
        return min(1.0, 0.65 * base_score + 0.35 * concept_score)
    return min(1.0, base_score)


class OfficialFAQIndex:
    def __init__(self, path: Path | str = DEFAULT_FAQ_PATH):
        self.path = Path(path)
        self.items = self._load()
        self._exact = {
            normalize_question(variant): item
            for item in self.items
            for variant in [item.get("question", ""), *(item.get("aliases") or [])]
            if variant
        }

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []

    def __len__(self) -> int:
        return len(self.items)

    def find_best(self, query: str, min_score: float = 0.0) -> dict | None:
        normalized_query = normalize_question(query)
        exact = self._exact.get(normalized_query)
        if exact:
            return {**exact, "score": 1.0, "match_type": "exact"}

        # '보건소', '지원', '예약'처럼 한 단어뿐인 질문은 여러 공식 문항과
        # 동시에 겹친다. 업무 개념도 없는 짧은 질문은 직접 답하지 않고 역질문한다.
        query_concepts = {concept for concept in _CONCEPTS if concept in normalized_query}
        if len(_tokens(query)) < 2 and not query_concepts:
            return None

        best_item = None
        best_score = 0.0
        for item in self.items:
            variants = [item.get("question", ""), *(item.get("aliases") or [])]
            score = max(question_similarity(query, variant) for variant in variants if variant)
            if score > best_score:
                best_item = item
                best_score = score
        if best_item is None or best_score < min_score:
            return None
        return {**best_item, "score": best_score, "match_type": "fuzzy"}

    def search_documents(self, query: str, limit: int = 5, min_score: float = 0.0) -> list[dict]:
        forced_ids = required_faq_ids(query)
        scored = []
        for item in self.items:
            variants = [item.get("question", ""), *(item.get("aliases") or [])]
            score = max(question_similarity(query, variant) for variant in variants if variant)
            if item.get("id") in forced_ids:
                score = 1.0
            if score >= min_score:
                scored.append((score, item))
        scored.sort(key=lambda row: (-row[0], row[1].get("id", 0)))

        documents = []
        for score, item in scored[:limit]:
            documents.append({
                "id": f"official-faq:{item.get('id')}",
                "content": f"질문: {item.get('question', '')}\n공식 답변: {item.get('answer', '')}",
                "metadata": {
                    "url": item.get("url", ""),
                    "title": item.get("question", "구청 공식 예상질문"),
                    "category": "official_faq",
                    "service_type": item.get("category", "기타"),
                    "source_priority": (
                        "priority_service"
                        if int(item.get("id", 0)) >= 1000
                        else "official_faq"
                    ),
                    "approved_answer": item.get("answer", ""),
                    "required_facts": item.get("required_facts", []),
                    "verified_at": item.get("verified_at", ""),
                    "is_time_sensitive": bool(item.get("is_time_sensitive", False)),
                },
                "similarity": score,
                "faq_score": score,
            })
        return documents
