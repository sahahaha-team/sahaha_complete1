"""부서·업무별 공식 전화번호를 빠르게 조회하는 경량 인덱스."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path


DEFAULT_CONTACT_PATH = (
    Path(__file__).resolve().parent.parent / "resources" / "department_contacts.json"
)
STAFF_SOURCE_URL = "https://www.saha.go.kr/portal/staff/list.do?mId=0604030000"

_INTENT_TERMS = (
    "담당자", "담당부서", "담당 부서", "부서", "연락처", "전화번호",
    "전화 번호", "문의처", "어디로 문의", "어디에 문의", "누가 담당",
)
_STOPWORDS = {
    "담당", "담당자", "담당부서", "부서", "연락처", "전화", "전화번호",
    "번호", "문의", "문의처", "알려줘", "알려주세요", "어디", "누구",
    "사하구", "사하구청", "업무", "관련", "은", "는", "이", "가",
}
_JOSA = ("으로", "에서", "에게", "이나", "거나", "하고", "은", "는", "이", "가", "을", "를", "와", "과", "로", "도", "만")


def _compact(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", (value or "").lower())


def _strip_josa(value: str) -> str:
    for suffix in _JOSA:
        if len(value) > len(suffix) + 1 and value.endswith(suffix):
            return value[:-len(suffix)]
    return value


def _query_terms(query: str) -> set[str]:
    terms: set[str] = set()
    for raw in re.findall(r"[0-9a-z가-힣]{2,}", (query or "").lower()):
        term = _strip_josa(raw)
        if term not in _STOPWORDS and len(term) >= 2 and not term.isdigit():
            terms.add(term)
    return terms


def _matching_duty_excerpt(duties: str, terms: set[str]) -> str:
    """전체 담당 업무 중 질문 내용어가 포함된 짧은 구절만 반환한다."""
    pieces = [piece.strip(" -·") for piece in re.split(r"[,;\n]+", duties or "") if piece.strip(" -·")]
    matches = [piece for piece in pieces if any(term in piece.lower() for term in terms)]
    if matches:
        matches.sort(key=lambda value: (len(value), value))
        return " · ".join(matches[:2])[:100]
    return (duties or "").strip()[:100]


def is_contact_lookup_question(query: str) -> bool:
    value = (query or "").lower()
    compact = _compact(value)
    asks_office_basics = (
        any(term in compact for term in ("사하구청", "구청"))
        and any(term in compact for term in ("위치", "주소", "대표", "오시는길"))
    )
    if asks_office_basics or any(term in value for term in ("대표전화", "대표 전화", "구청 연락처")):
        return False
    return any(term in value for term in _INTENT_TERMS)


def build_contact_payload(staff_data: dict) -> dict:
    """전체 직원 스냅샷에서 전화 검색에 필요한 필드만 추린다."""
    departments = []
    for row in staff_data.get("departments") or []:
        name = str(row.get("name") or "").strip()
        phone = str(row.get("phone") or "").strip()
        if name and phone:
            departments.append({"name": name, "phone": phone})

    contacts = []
    seen = set()
    for row in staff_data.get("rows") or []:
        department = str(row.get("department") or "").strip()
        title = str(row.get("title") or "").strip()
        phone = str(row.get("phone") or "").strip()
        duties = re.sub(r"\s+", " ", str(row.get("duties") or "")).strip()
        key = (department, title, phone, duties)
        if not department or not phone or not duties or key in seen:
            continue
        seen.add(key)
        contacts.append({
            "department": department,
            "title": title,
            "phone": phone,
            "duties": duties,
        })

    return {
        "source_url": staff_data.get("source_url") or STAFF_SOURCE_URL,
        "generated_at": staff_data.get("generated_at") or "",
        "departments": sorted(departments, key=lambda row: row["name"]),
        "contacts": sorted(
            contacts,
            key=lambda row: (row["department"], row["title"], row["phone"], row["duties"]),
        ),
    }


def save_contact_payload(staff_data: dict, path: Path = DEFAULT_CONTACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_contact_payload(staff_data)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    load_contact_payload.cache_clear()
    return path


@lru_cache(maxsize=2)
def load_contact_payload(path: str = str(DEFAULT_CONTACT_PATH)) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        return {"source_url": STAFF_SOURCE_URL, "departments": [], "contacts": []}
    return json.loads(file_path.read_text(encoding="utf-8"))


class ContactDirectory:
    def __init__(self, path: Path | str = DEFAULT_CONTACT_PATH):
        self.path = Path(path)
        self.data = load_contact_payload(str(self.path))
        self.source_url = self.data.get("source_url") or STAFF_SOURCE_URL

    def lookup(self, query: str, limit: int = 5) -> dict:
        """명확한 1건은 match, 후보가 겹치면 ambiguous, 없으면 none을 반환한다."""
        if not is_contact_lookup_question(query):
            return {"status": "none", "results": []}

        compact_query = _compact(query)
        for row in self.data.get("departments") or []:
            name = str(row.get("name") or "").strip()
            if name and _compact(name) in compact_query:
                result = {
                    "department": name,
                    "title": "부서 대표번호",
                    "phone": str(row.get("phone") or "").strip(),
                    "duties": f"{name} 소관 업무",
                    "score": 10.0,
                    "source_url": self.source_url,
                }
                return {"status": "match", "results": [result]}

        terms = _query_terms(query)
        if not terms:
            return {"status": "ambiguous", "results": []}

        scored: list[tuple[float, dict]] = []
        for row in self.data.get("contacts") or []:
            department = str(row.get("department") or "").lower()
            title = str(row.get("title") or "").lower()
            duties = str(row.get("duties") or "").lower()
            score = 0.0
            matched = 0
            for term in terms:
                if term in duties:
                    score += 2.0
                    matched += 1
                elif term in department:
                    score += 1.5
                    matched += 1
                elif term in title:
                    score += 1.0
                    matched += 1
            if matched:
                score += matched / max(1, len(terms))
                scored.append((score, row))

        scored.sort(key=lambda item: (-item[0], item[1].get("department", ""), item[1].get("phone", "")))
        results = []
        for score, row in scored[:limit]:
            results.append({
                **row,
                "duties": _matching_duty_excerpt(str(row.get("duties") or ""), terms),
                "score": round(score, 3),
                "source_url": self.source_url,
            })
        if not results or results[0]["score"] < 2.0:
            return {"status": "ambiguous", "results": results}

        top = results[0]
        competing = [
            row for row in results[1:]
            if top["score"] - row["score"] < 0.75
            and (row.get("phone"), row.get("duties")) != (top.get("phone"), top.get("duties"))
        ]
        return {
            "status": "ambiguous" if competing else "match",
            "results": results,
        }

    @staticmethod
    def clarification(result: dict) -> dict:
        candidates = result.get("results") or []
        examples = []
        suggestions = []
        for row in candidates[:3]:
            duty = str(row.get("duties") or "").strip()
            if duty and duty not in examples:
                examples.append(duty[:35])
                suggestions.append(f"{duty[:25]} 담당 전화번호 알려줘")
        suffix = f" 예: {', '.join(examples)}" if examples else ""
        return {
            "answer": f"전화번호를 찾을 업무명을 한 가지만 알려주세요.{suffix}",
            "suggested_questions": suggestions,
        }
