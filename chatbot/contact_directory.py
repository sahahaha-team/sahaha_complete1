"""Fast contact answers from a local official snapshot. No LLM, DB or network."""
from __future__ import annotations

import json
import math
import re
import threading
import time
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import lru_cache

from chatbot.privacy import detect_personal_info

DIRECTORY_PATH = Path(__file__).resolve().parents[1] / "data" / "department_contacts.json"
MAX_AGE = timedelta(days=7)
WEAK_TERMS = set("업무 담당 부서 전화 번호 문의 연락 안내 총괄 관리 지원 사업 신청 접수 발급 신고 처리 민원 운영 관련 기타 행정 직원 사하 구청 부산 주민 담당자 교육 시설 업무총괄".split())
# These are wording equivalents only; departments and numbers always come from the file.
SYNONYMS = {
    "인공지능": "ai", "보건증": "건강진단결과서",
    "출산장려금": "출산지원금", "불법주차": "불법주정차",
    "대형쓰레기": "대형폐기물", "불법건축물": "위반건축물", "주민센터": "행정복지센터",
}
INTENT = re.compile(r"연락처|전화|담당부서|담당자|담당.*(?:알려|누구|어디)|문의처|연결|어느(?:부서|과)|어떤부서|부서.*(?:알려|어디)|(?:번호|문의).*(?:알려|어디|뭐|어떻게|할곳)")
FILLER = re.compile(r"사하구청|사하구|부산광역시|부산|담당부서|담당자|담당|대표전화|대표번호|대표|전화번호|연락처|전화|번호|부서|문의처|업무내용|업무|문의|알려(?:주실수있(?:나요|어요)|주세요|줘|주실래|줄래)?|어떻게(?:돼|되나요|되는지|되요)?|뭐(?:야|예요|에요|지)?|몇번(?:인가요|이야|인지)?|어디로|어디에|어디|어느과|어느|어떤|무슨|연결|관련|관한|알고싶(?:어요|어)|알수있(?:을까요|을까|나요)|해야(?:해|하나요)|할수있(?:나요|어요)|부탁(?:해|드려요)|인가요|있나요|주세요|필요해요|궁금해요|좀|신고|신청|접수|발급|처리")
PARTICLES = re.compile(r"(?:으로|에서|에게|까지|하고|좀|하는|하려고|하려면|하려|할때|은|는|이|가|을|를|의|로|에|도|요)$")


def duty_excerpt(duties: str, terms: set[str]) -> str:
    """Keep short duties verbatim, including every region inside parentheses."""
    if len(duties) <= 450:
        return duties
    chunks, current, depth = [], [], 0
    for char in duties:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        if depth == 0 and char in "\n•○,;":
            chunks.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    chunks.append("".join(current).strip())
    relevant = [chunk for chunk in chunks if any(term in canonical(chunk) for term in terms)]
    return " / ".join(relevant) or duties


def compact(text: str) -> str:
    return re.sub(r"[^가-힣a-z0-9]", "", text.lower())


def canonical(text: str) -> str:
    value = compact(text)
    for alias, target in SYNONYMS.items():
        value = value.replace(alias, target)
    return value


def fresh(timestamp: str) -> bool:
    try:
        checked = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - MAX_AGE <= checked <= datetime.now(timezone.utc) + timedelta(minutes=5)
    except (ValueError, TypeError, AttributeError):
        return False


def response(answer: str, sources: list | None = None, *, clarification=False, reason=None,
             suggestions: list | None = None, details: str = "") -> dict:
    sources = sources or []
    return {
        "answer": answer, "answer_details": details, "sources": sources, "is_clarification": clarification,
        "degraded": reason is not None, "degraded_reason": reason,
        "evidence": {"status": "official" if sources else "clarification" if clarification else "insufficient",
                     "label": "공식 연락처 파일에서 확인됨" if sources else "문의 업무 확인 필요",
                     "official_source_count": len({s["url"] for s in sources})},
        "suggested_questions": suggestions or [],
    }


class ContactDirectoryResponder:
    def __init__(self, path: Path = DIRECTORY_PATH):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._stamp = None
        self.data = {}
        self.departments = []
        self.rows = []
        self.vocabulary = set()
        self.frequencies = Counter()
        self._contexts = OrderedDict()

    def _load(self):
        """Only read again when an atomic file replacement changes its stat."""
        try:
            stat = self.path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            if self._stamp == stamp:
                return
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("schema_version") != 1 or not data.get("departments"):
                raise ValueError("Invalid contact directory")
            rows, vocabulary, frequencies = [], set(), Counter()
            for dept in data["departments"]:
                for record in dept.get("contacts", []):
                    # No fallback to another person's number or the fax column.
                    if not re.fullmatch(r"051-\d{3,4}-\d{4}(?:~\d{1,4})?", record.get("phone", "")):
                        continue
                    terms = {canonical(k) for k in record.get("keywords", [])}
                    terms -= WEAK_TERMS
                    # A department's name inside '민원여권과 업무 총괄' does
                    # not establish that its head personally handles passports.
                    row = {**record, "department": dept["name"], "terms": terms,
                           "text": canonical(record["duties"].replace(dept["name"], "")),
                           "role": canonical(record["title"].replace(dept["name"], ""))}
                    rows.append(row)
                    vocabulary.update(terms)
                    frequencies.update(terms)
            self.data, self.departments, self.rows = data, data["departments"], rows
            self.vocabulary, self.frequencies = vocabulary, frequencies
            self._stamp = stamp
        except (OSError, ValueError, KeyError, TypeError):
            # A missing/broken file must never fall through to AI guessing.
            self.data, self.departments, self.rows = {}, [], []
            self.vocabulary, self.frequencies, self._stamp = set(), Counter(), None

    def clear(self, session_id: str):
        with self._lock:
            self._contexts.pop(session_id, None)

    def remember(self, session_id: str, subject: str):
        self._contexts[session_id] = (time.monotonic(), subject)
        self._contexts.move_to_end(session_id)
        while len(self._contexts) > 1000:
            self._contexts.popitem(last=False)

    def observe(self, session_id: str, query: str):
        """A subsequent '그 업무 전화번호는?' can reuse the last user topic."""
        if not detect_personal_info(query, use_ner=False):
            with self._lock:
                self.remember(session_id, query)

    def _source(self, department: str, contact: str, representative=False) -> dict:
        prefix = "representative" if representative else "staff"
        return {"title": "사하구청 부서별 대표전화" if representative else "사하구청 직원업무안내",
                "url": self.data[f"{prefix}_source_url"], "category": "contact_directory",
                "source_type": "official_page", "department": department, "contact": contact,
                "checked_at": self.data[f"{prefix}_checked_at"]}

    def _representative(self, dept: dict) -> dict:
        phone = dept.get("representative_phone", "")
        if phone and fresh(self.data.get("representative_checked_at")):
            return response(f"**{dept['name']} 대표전화: {phone}**\n\n공식 부서별 전화번호 안내에서 확인한 번호입니다.",
                            [self._source(dept["name"], phone, representative=True)])
        # Some centers/dongs have no representative in the official phone guide.
        heads = [r for r in self.rows if r["department"] == dept["name"]
                 and re.search(r"(?:과장|실장|동장|관장|소장)$", r["title"])]
        if len(heads) == 1 and fresh(self.data.get("staff_checked_at")):
            row = heads[0]
            return response(f"**{dept['name']}**\n\n- {row['title']} 직통전화: **{row['phone']}**\n- 업무: {row['duties']}\n\n공식 전화번호 표에 대표번호가 없어 직원업무안내에 기재된 직통번호를 안내합니다.",
                            [self._source(dept["name"], row["phone"])])
        return response(f"현재 공식 파일에서 **{dept['name']} 대표번호**를 확인할 수 없습니다. 사하구청 대표전화 **051-220-4000**에서 연결받아 주세요.", reason="contact_not_verified")

    def respond(self, session_id: str, query: str) -> dict | None:
        text = compact(query)
        # Location + organization contact is a compound administrative query.
        # Let the original-page answer include the verified main number.
        from chatbot.official_faq import required_faq_ids
        if required_faq_ids(query) == {1, 2}:
            return None
        # Phone-number administration is a procedure question, unless it also
        # explicitly asks which office to contact.
        if re.search(r"(?:전화번호|연락처).{0,2}(?:변경|등록|수정|삭제)", text) and not re.search(r"담당부서|문의처|어느과", text):
            return None
        if re.search(r"담당자(?:가|는|에게|와)", text) and not re.search(r"전화|연락처|번호|어느부서", text):
            return None
        wants_contact = bool(INTENT.search(text)) or bool(re.search(r"담당.*번호|번호.*담당|번호(?:는|몇|좀|$)", text))
        # A bare department name is also a valid answer to a choice prompt.
        bare_department = bool(re.fullmatch(r"[가-힣0-9]+(?:과|실|동|보건소)", text))
        if not wants_contact and not bare_department:
            return None
        personal = detect_personal_info(query, use_ner=False)
        if personal:
            result = response(f"입력에 {personal}(으)로 보이는 개인정보가 포함되어 있습니다. 개인정보를 지우고 문의 업무만 입력해주세요.")
            result["evidence"] = {"status": "protected", "label": "개인정보 보호됨", "official_source_count": 0}
            return result
        with self._lock:
            self._load()
            if not self.data:
                return response("공식 연락처 파일을 읽을 수 없습니다. 사하구청 대표전화 **051-220-4000**로 문의해주세요.", reason="contact_directory_unavailable")
            if not wants_contact and not any(compact(d["name"]) == text for d in self.departments):
                return None
            return self._answer(session_id, query)

    def _answer(self, session_id: str, query: str, contextual=False) -> dict:
        text = canonical(query)
        if re.search(r"^(?:(?:사하구청|사하구|구청))?대표(?:전화|번호)", text):
            phone = self.data.get("organization_phone", "")
            if phone and fresh(self.data.get("representative_checked_at")):
                return response(f"**사하구청 대표전화: {phone}**", [self._source("사하구청", phone, representative=True)])
            return response("현재 대표전화 자료의 최신 확인이 필요합니다.", reason="contact_not_verified")
        departments = [d for d in self.departments if compact(d["name"]) in text]
        # Longer official names take precedence when one is contained in another.
        departments = [d for d in departments if not any(d["name"] != e["name"] and d["name"] in e["name"] for e in departments)]
        subject = text
        for dept in departments:
            subject = subject.replace(compact(dept["name"]), "")
        subject = FILLER.sub("", subject)
        subject = re.sub(r"(?:받|하)(?:으려는데요?|려고하는데|려는데요?|으려면|려고|려면|려는|려고해|고싶어요?|고싶은데요?)", "", subject)
        if contextual:
            subject = re.sub(r"수수료|요금|금액|비용|얼마(?:야|인가요|예요|인지)?", "", subject)
        subject = re.sub(r"^(?:그러면|그럼)", "", subject)
        # A dong in a work question specifies the service area, whereas a
        # dong alone asks for that office's phone. Keep these cases separate.
        area_names = {re.sub(r"[1-4]?동$", "", d["name"]) for d in self.departments if d["name"].endswith("동")}
        areas = {name for name in area_names if re.search(re.escape(name) + r"(?:[1-4])?동", text)}
        for area in areas:
            subject = re.sub(re.escape(area) + r"(?:[1-4])?동", "", subject)
        previous = None
        while previous != subject:
            previous, subject = subject, PARTICLES.sub("", subject)
        if subject in {"그", "그럼", "그부서", "그업무", "거기", "그러면", "", "해", "인"}:
            if departments:
                self.remember(session_id, query)
                if len(departments) > 1:
                    return response("어느 부서의 전화번호가 필요한가요? " + ", ".join(d["name"] for d in departments), clarification=True,
                                    suggestions=[d["name"] + " 전화번호 알려줘" for d in departments])
                return self._representative(departments[0])
            context = self._contexts.get(session_id)
            if not contextual and context and time.monotonic() - context[0] < 1800:
                return self._answer(session_id, context[1], contextual=True)
            return response("문의할 업무나 부서명을 알려주세요. 예: ‘건축과 전화번호’, ‘여권 담당 부서 연락처’.", clarification=True,
                            suggestions=["건축과 전화번호", "여권 담당 부서 연락처"])

        if not fresh(self.data.get("staff_checked_at")):
            return response("직원업무안내 확인일이 7일을 지나 최신 담당자를 확인할 수 없습니다. 사하구청 대표전화 **051-220-4000**로 확인해주세요.", reason="stale_contact_directory")
        departments = [d for d in departments if not d["name"].endswith("동")]
        found = {k for k in self.vocabulary if k in subject and len(k) >= 2}
        # A complete noun ('대형폐기물') carries more meaning than its fragments.
        terms = {k for k in found if not any(k != longer and k in longer for longer in found)}
        remainder = subject
        for term in sorted(found, key=len, reverse=True):
            remainder = remainder.replace(term, "")
        for filler in ("알려", "곳", "랑", "와", "및", "어떻게", "해야해", "합니다", "해주세요", "하면돼", "좀", "찾아줘", "원해", "부탁해"):
            remainder = remainder.replace(filler, "")
        remainder = PARTICLES.sub("", remainder)
        if len(remainder) >= 4:
            return response("질문의 일부 업무를 공식 직원업무안내에서 확인하지 못했습니다. 필요한 업무명을 구체적으로 알려주세요.", clarification=True, reason="contact_not_verified")
        if not terms:
            return response("해당 업무의 담당 부서와 번호를 공식 파일에서 확인하지 못했습니다. 문의 내용을 조금 더 구체적으로 알려주세요. 사하구청 대표전화는 **051-220-4000**입니다.", clarification=True, reason="contact_not_verified")

        ranked = []
        for row in self.rows:
            if departments and row["department"] not in {d["name"] for d in departments}:
                continue
            if areas and not any(area in row["text"] or area in row["department"] for area in areas):
                continue
            # Every meaningful query term must be supported by this actual duty/role.
            if not all(term in row["text"] or term in row["role"] for term in terms):
                continue
            score = sum(math.log(1 + len(self.rows) / (1 + self.frequencies[term])) for term in terms)
            score += 1.0 if any(term in row["role"] for term in terms) else 0
            if any(action in text and action in row["text"] for action in ("접수", "교부", "발급")):
                score += 1.5
            # Without a named dong, central departmental specialists are preferred.
            if re.search(r"\d동$", row["department"]):
                score -= 2.0
            ranked.append((score, row))
        if not ranked:
            return response("질문에 해당하는 업무와 전화번호를 함께 확인하지 못했습니다. 업무나 대상 지역을 구체적으로 알려주세요.", clarification=True, reason="contact_not_verified")
        ranked.sort(key=lambda item: (-item[0], len(item[1]["duties"]), item[1]["phone"]))
        best_score = ranked[0][0]
        candidates = [row for score, row in ranked if score >= best_score - 0.5]
        names = list(dict.fromkeys(row["department"] for row in candidates))
        if len(names) > 1:
            options = []
            for name in names[:3]:
                example = next(row for row in candidates if row["department"] == name)
                scope = duty_excerpt(example["duties"], terms)
                scope = scope if len(scope) <= 90 else example["title"]
                options.append(f"- **{name}**: {scope}")
            return response("**어떤 업무나 지역**에 해당하나요?\n\n" + "\n".join(options),
                            clarification=True, suggestions=[f"{name} {subject} 담당 전화번호" for name in names[:5]])
        self.remember(session_id, query)
        chosen, used_phones = [], set()
        for row in candidates:
            if row["phone"] not in used_phones:
                chosen.append(row)
                used_phones.add(row["phone"])
        # Never silently omit equally plausible contacts: ask for narrower scope.
        if len(chosen) > 3:
            dept = next(d for d in self.departments if d["name"] == names[0])
            phone = dept.get("representative_phone") if fresh(self.data.get("representative_checked_at")) else ""
            sources = [self._source(names[0], phone, representative=True), self._source(names[0], "")] if phone else []
            return response(f"**담당 부서: {names[0]}**\n\n" + (f"대표전화: **{phone}**\n\n" if phone else "") +
                            "관련 담당자가 여러 명 있습니다. 직통번호를 찾으려면 세부 업무나 동을 알려주세요.",
                            sources, clarification=True, suggestions=[f"{names[0]} {subject} 담당 업무 알려줘"])
        lines = [f"**{names[0]}**"]
        details = []
        for row in chosen:
            duty = duty_excerpt(row["duties"], terms)
            lines.append(f"- **{row['phone']}** ({row['title']})")
            if len(duty) <= 150 and len(chosen) == 1:
                lines.append(duty)
            details.append(f"{row['title']} · {row['phone']}\n\n{row['duties']}")
        if len(chosen) > 1:
            lines.append("업무 범위와 담당 지역에 맞는 번호로 문의해주세요.")
        return response("\n\n".join(lines), [self._source(row["department"], row["phone"]) for row in chosen],
                        details="\n\n".join(details))


contact_responder = ContactDirectoryResponder()


# Portable staff-index API used by the team export/evaluation scripts.
# Resident replies use ContactDirectoryResponder and its verified representative table.
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
