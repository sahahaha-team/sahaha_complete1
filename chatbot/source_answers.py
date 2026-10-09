"""Return source passages without allowing the LLM to rewrite factual claims."""

from __future__ import annotations

import re
import hashlib

from chatbot.evidence import is_answerable_document, topic_support
from chatbot.question_intent import asks_opening_hours, has_opening_hours, asks_location, has_location
from chatbot.vaccination import vaccination_section, vaccination_place_brief
from chatbot.source_text import clean_source_text


def strip_page_chrome(text: str) -> str:
    return clean_source_text(text)


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
            result = start + body.split(start, 1)[1].split(end, 1)[0]
            existing = next((line for line in body.splitlines() if re.search(r'유효기간\s*남은\s*여권.*지참', line)), '')
            return result + ('\n' + existing if existing else '')
    if "mId=0309060000" in url and "법률상담" in compact and "사하구" in compact:
        if "\n기타 법률상담 안내" not in body:
            return ""
        return body.split("\n기타 법률상담 안내", 1)[0]
    if "mId=0604050000" in url and any(word in compact for word in ("위치", "어디", "주소", "연락처", "대표전화")):
        start, end = "주소 및 전화 안내\n", "\n버스이용시"
        if start in body and end in body:
            return start + body.split(start, 1)[1].split(end, 1)[0]
    return None


def build_source_answer(documents: list[dict], client, *, query: str = "", topic_keywords: set[str] | None = None) -> tuple[str, list[dict]]:
    """Try the next relevant source if the leading chunk's original is unsuitable."""
    if documents and documents[0].get('metadata', {}).get('navigation_catalog'):
        selected = []
        for document in documents:
            words = set(document['metadata'].get('navigation_topics') or topic_keywords or [])
            answer, used = _build_one_source_answer([document], client, query=query, topic_keywords=words)
            if answer and used:
                selected.append(document)
        if selected:
            body = '\n'.join('> - ' + d['metadata']['navigation_catalog'] for d in selected)
            return '공식 홈페이지의 서비스 안내입니다.\n\n' + body + '\n\n아래 공식 출처에서 이용 안내를 확인하세요.', selected
    for document in documents[:5]:
        answer, used = _build_one_source_answer([document], client, query=query, topic_keywords=topic_keywords)
        if answer:
            return answer, used
    return "", []


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
        try:
            rows = client.table("raw_pages").select("content,title").eq("url", url).limit(1).execute().data or []
            text = rows[0].get("content") or "" if rows else ""
        except Exception:
            text = ""
    if not text.strip():
        return "", []
    # A later retrieval chunk may omit the board header. Check the complete
    # original too, so pagination/search fields cannot masquerade as an answer.
    if not is_answerable_document(query, {"content": text, "metadata": meta}):
        return "", []
    current_title = str(rows[0].get('title') or '')
    if meta.get('page_document') and meta.get('content_hash') == hashlib.sha256(text.encode()).hexdigest():
        current_title += ' ' + str(meta.get('title') or '')
    if topic_keywords is not None and not topic_support(
            {"content": strip_page_chrome(text), 'metadata': {'title': current_title}}, topic_keywords)[0]:
        return "", []
    section = focused_section(query, str(url or ""), text)
    if section == "":
        return "", []
    if meta.get('page_document') and section is None:
        from chatbot.page_answers import select_sections
        current_version = meta.get('content_hash') == hashlib.sha256(text.encode()).hexdigest()
        current_sections = (meta.get('page_sections') or []) if current_version else []
        section, heading = select_sections(query, text, current_sections,
                                           topic_keywords or set(), meta.get('query_tokens') or [])
        meta = {**meta, 'selected_page_heading': heading}
        if not current_version:
            meta = {**meta, 'title': current_title, 'page_sections': []}
        lead = {**lead, 'metadata': meta}
    structured = strip_page_chrome(str(meta.get('section_text') or ''))
    if structured != meta.get('section_text', ''):
        meta = {**meta, 'section_text': structured}
        lead = {**lead, 'metadata': meta}
    if (section is None and structured and len(structured) >= 35 and
            meta.get('content_hash') == hashlib.sha256(text.encode()).hexdigest()):
        passage = str(meta.get('section_heading') or '') + '\n' + structured
    else:
        passage = section if section is not None else source_passage(text, lead.get("content") or "")
    if asks_opening_hours(query) and not has_opening_hours(passage):
        return "", []
    if asks_location(query) and not has_location(passage) and not meta.get('page_document'):
        return "", []
    if (section is not None and asks_location(query)
            and any(mid in str(url) for mid in ('mId=0203020000', 'mId=0203020100'))
            and not vaccination_place_brief(query, str(url), passage.splitlines())):
        return "", []
    from chatbot.question_intent import asks_navigation
    # Complete pages were validated against the current original above.
    # A selected date/age field can use pronouns or omit the service name;
    # requiring every topic again would discard the correct field and fall
    # through to an unrelated attachment that merely repeats those names.
    if topic_keywords is not None and not meta.get('page_document') and not asks_navigation(query) and not topic_support(
            {"content": passage, "metadata": {'title': meta.get('title','')}}, topic_keywords)[0]:
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
