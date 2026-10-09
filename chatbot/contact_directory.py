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

from chatbot.privacy import detect_personal_info
from chatbot.service_navigation import is_council_location_query

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
# Remove complete contact-question phrases before individual filler words.
# Otherwise '담당하는 곳이 어디야' leaves '하는곳이야' as an unknown duty.
CONTACT_PHRASES = re.compile(
    r"(?:사하구청|사하구|부산광역시|부산)(?:에서는|에서|의|에)"
    r"|담당(?:하고있는|하는)(?:곳|부서|팀|과)(?:이|가|은|는)?"
    r"|어디(?:인가요|인지|예요|에요|야|죠|니)"
)


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
        if is_council_location_query(query):
            return None  # Location + phone is a building guide, not a staff duty.
        text = compact(query)
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
        subject = CONTACT_PHRASES.sub("", text)
        for dept in departments:
            subject = re.sub(re.escape(compact(dept["name"])) + r"(?:에서는|에서|의|에)?", "", subject)
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
