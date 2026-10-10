"""Return source passages without allowing the LLM to rewrite factual claims."""

from __future__ import annotations

import re

from chatbot.evidence import is_answerable_document, topic_support, is_service_source
from chatbot.answer_goal import answer_goal
from chatbot.question_intent import asks_opening_hours, has_opening_hours, asks_location, has_location
from chatbot.vaccination import vaccination_section, vaccination_place_brief


def strip_page_chrome(text: str) -> str:
    text = (text or "").replace("\r", "")
    if "인쇄하기\n" in text:
        text = text.split("인쇄하기\n", 1)[1]
    if "\n만족도조사\n" in text:
        text = text.split("\n만족도조사\n", 1)[0]
    # Standalone icon/escape remnants are not administrative source content.
    lines = [line for line in text.splitlines()
             if not re.fullmatch(r'(?:svg|img|[>\\ ]+)', line.strip(), re.IGNORECASE)]
    return re.sub(r"[ \t]+", " ", '\n'.join(lines)).strip()


def source_passage(text: str, anchor: str, *, budget: int = 2400) -> str:
    """Keep contiguous original lines, including nearby qualifications and headings."""
    text = strip_page_chrome(text)
    if len(text) <= budget:
        return text
    # Chunk cleaning can remove symbols. Find its longest substantive line in
    # the original instead of constructing a new sentence from several cells.
    lines = sorted((line.strip() for line in (anchor or "").splitlines()
                    if len(line.strip()) >= 12), key=len, reverse=True)
    position = next((text.find(line) for line in lines if line in text), 0)
    start = max(0, position - 400)
    start = text.rfind("\n", 0, start) + 1 if start else 0
    end = min(len(text), start + budget)
    if end < len(text):
        boundary = text.rfind("\n", start, end)
        end = boundary if boundary > start else end
    passage = text[start:end].strip()
    return ("[…]\n" if start else "") + passage + ("\n[…]" if end < len(text) else "")


def focused_section(query: str, url: str, text: str) -> str | None:
    """Keep neighboring service types apart on multi-service pages.

    None means no section rule applies; an empty string means an expected
    structure changed and we must abstain instead of guessing another section.
    """
    compact = re.sub(r"\s+", "", query or "")
    body = strip_page_chrome(text)
    vaccine_section = vaccination_section(query, url, body)
    if vaccine_section is not None:
        return vaccine_section
    if "mId=0403080000" in url and "신고" in compact and not any(
            word in compact for word in ("이의", "의견진술", "과태료", "견인", "납부")):
        start = "불법주정차 주민신고제 운영 안내(변경)\n"
        if start not in body:
            return ""
        return start + body.rsplit(start, 1)[1]
    if "mId=0104020000" in url and "여권" in compact:
        if any(word in compact for word in ('미성년', '아이', '18세미만', '자녀')) and any(word in compact for word in ('서류', '준비')):
            start, end = '만18세 미만 미성년자의 여권 신청\n', '\n긴급여권'
            if start not in body or end not in body:
                return ''
            section = body.split(start, 1)[1].split(end, 1)[0]
            marker = '친권자' if any(word in compact for word in ('부모', '친권자', '법정대리인')) else '미성년자 본인' if '본인' in compact else '미성년자의 2촌 이내 친족' if '친족' in compact else ''
            selected = next((line for line in section.splitlines() if marker and line.startswith(marker)), None)
            common = next((line for line in body.splitlines() if line.startswith('미성년자의 사진 및 구여권')), None)
            return start + common + '\n' + selected if common and selected else ''
        if any(word in compact for word in ("발급기간", "기간은", "며칠", "소요")) and "유효기간" not in compact:
            start = "\n여권교부\n"
            if start not in body:
                return ""
            return "여권교부\n" + body.rsplit(start, 1)[1]
        if "재발급" in compact and any(word in compact for word in ("준비", "서류")) and not any(
                word in compact for word in ("미성년", "아이", "긴급", "관용")):
            start, end = "\n재발급\n", "\n여권발급 등에 관한 수수료"
            if start not in body or end not in body:
                return ""
            return "재발급\n" + body.split(start, 1)[1].split(end, 1)[0]
        if (any(word in compact for word in ("새로", "처음", "신규"))
                and any(word in compact for word in ("준비", "서류"))
                and not any(word in compact for word in ("미성년", "아이", "긴급", "관용", "재발급"))):
            start, end = "신규발급\n일반여권\n", "\n만18세 미만 미성년자의 여권 신청"
            if start not in body or end not in body:
                return ""
            return start + body.split(start, 1)[1].split(end, 1)[0]
    if "mId=0309060000" in url and "법률상담" in compact and "사하구" in compact:
        if "\n기타 법률상담 안내" not in body:
            return ""
        return body.split("\n기타 법률상담 안내", 1)[0]
    if "mId=0604050000" in url and any(word in compact for word in ("위치", "어디", "주소", "연락처", "대표전화")):
        start, end = "주소 및 전화 안내\n", "\n버스이용시"
        if start in body and end in body:
            return start + body.split(start, 1)[1].split(end, 1)[0]
    return None


def build_source_answer(documents: list[dict], client, *, query: str = "", topic_keywords: set[str] | None = None,
                        require_brief: bool = False) -> tuple[str, list[dict]]:
    """Try the next relevant source if the leading chunk's original is unsuitable."""
    fallback = ("", [])
    seen = set()
    for document in documents:
        url = (document.get("metadata") or {}).get("url")
        if url in seen:
            continue
        seen.add(url)
        answer, used = _build_one_source_answer([document], client, query=query, topic_keywords=topic_keywords)
        if answer:
            if not require_brief:
                return answer, used
            from chatbot.concise_answers import concise_source_answer
            brief = concise_source_answer(query, answer, used, topic_keywords or set())
            if not brief["is_clarification"]:
                return answer, used
            if not fallback[0]:
                fallback = answer, used
    return fallback


def _build_one_source_answer(documents: list[dict], client, *, query: str = "", topic_keywords: set[str] | None = None) -> tuple[str, list[dict]]:
    """Use one leading source so separate programs cannot be merged into a claim.

    The full raw page provides surrounding conditions that a 500-character
    retrieval chunk might omit. If it is unavailable, fail closed.
    """
    if not documents:
        return "", []
    lead = documents[0]
    meta = lead.get("metadata") or {}
    url = meta.get("url")
    if topic_keywords is not None and not is_service_source(query, lead, topic_keywords):
        return "", []
    if meta.get("category") == "staff_directory":
        dept = str(meta.get("department") or "").strip()
        role = str(meta.get("title") or "").strip()
        phone = str(meta.get("contact") or "").strip()
        if not dept or not lead.get("content"):
            return "", []
        answer = f"공식 직원업무안내에서 확인한 담당 부서는 **{dept}**입니다."
        if role:
            answer += f"\n\n- 담당 직위: **{role}**"
        if phone:
            answer += f"\n- 연락처: **{phone}**"
        # Duties are copied from the verified row, never rewritten by a model.
        duties = str(lead.get("content") or "").split("업무: ", 1)
        if len(duties) == 2:
            answer += "\n\n담당 업무:\n" + "\n".join("> " + line for line in duties[1].splitlines())
        return answer, [lead]
    else:
        from chatbot.source_pages import source_document
        text, lead = source_document(lead, client)
        meta = lead.get('metadata') or {}
    if not text.strip():
        return "", []
    # A later retrieval chunk may omit the board header. Check the complete
    # original too, so pagination/search fields cannot masquerade as an answer.
    if not is_answerable_document(query, {"content": text, "metadata": meta}):
        return "", []
    if topic_keywords is not None and not topic_support(
            {"content": strip_page_chrome(text), "metadata": {"url": url}}, topic_keywords)[0]:
        return "", []
    section = focused_section(query, str(url or ""), text)
    if section == "":
        return "", []
    passage = section if section is not None else source_passage(text, lead.get("content") or "",
        budget=12000 if meta.get("source_type") == "crawled_page" else 2400)
    if asks_opening_hours(query) and not has_opening_hours(passage):
        return "", []
    if answer_goal(query) == "location" and not has_location(passage):
        from chatbot.reference_answers import reference_answer
        if not reference_answer(query, lead, passage, topic_keywords or set()):
            return "", []
    if (section is not None and asks_location(query)
            and any(mid in str(url) for mid in ('mId=0203020000', 'mId=0203020100'))
            and not vaccination_place_brief(query, str(url), passage.splitlines())):
        return "", []
    passage_meta = {"url": url}
    if topic_keywords and topic_keywords.issubset({"구청", "보건소"}):
        passage_meta["title"] = meta.get("title") or ""
    if topic_keywords is not None and not topic_support(
            {"content": passage, "metadata": passage_meta}, topic_keywords)[0]:
        return "", []
    title = str(meta.get("title") or "사하구청 안내")
    if meta.get("source_type") == "official_report":
        intro = (f"{title}의 원문입니다.\n"
                 f"자료 기준 기간: {meta.get('data_period', '미상')}\n"
                 f"보고서 작성일: {meta.get('issued_at', '미상')}")
    else:
        intro = f"{title}의 공식 안내 원문입니다."
    # No free-form model output enters this answer. Each quoted line comes
    # from a single source; omissions are explicit, never silently joined.
    quote = "\n".join("> " + line for line in passage.splitlines())
    return f"{intro}\n\n{quote}\n\n전체 조건은 아래 출처에서 확인할 수 있습니다.", [lead]
