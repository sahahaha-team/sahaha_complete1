"""Deterministic answers for tables where nearby programs have different amounts."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from config import SOURCE_DYNAMIC_MAX_AGE_DAYS
from chatbot.answer_completion import balanced

_BIRTH_URL = "https://www.saha.go.kr/portal/contents.do?mId=0510070100"
_HEALTH_FEE_URL = "https://www.saha.go.kr/health/contents.do?mId=0301030000"
_KIOSK_URL = "https://www.saha.go.kr/portal/contents.do?mId=0103040000"
_PASSPORT_URL = "https://www.saha.go.kr/portal/contents.do?mId=0104020000"
_WASTE_URL = "https://www.saha.go.kr/portal/contents.do?mId=0405050103"
_RECYCLING_URL = "https://www.saha.go.kr/portal/contents.do?mId=0405050101"


def parse_disposal_schedule(content: str, query: str) -> str | None:
    """Read the verified seven-column row; abstain if its structure changes.

    The HTML table's Monday-to-Sunday column order and absence of merged
    cells were checked on 2026-10-08. Never align arbitrary flattened cells.
    """
    header = r"배출요일\s*월\s*화\s*수\s*목\s*금\s*토\s*일\s*쓰레기\s*종류\s*"
    combustible = r"일반쓰레기\s*\(가연성\)\s*음식물쓰레기"
    pattern = (header + r"(?P<mon>재활용품\s*\(.*?)\s*(?P<tue>" + combustible + r")\s*"
               r"(?P<wed>재활용품\s*\(.*?)\s*(?P<thu>" + combustible + r")\s*"
               r"(?P<fri>배출\s*금지)\s*(?P<sat>배출\s*금지)\s*(?P<sun>"
               + combustible + r")\s*이럴때는 쓰레기를 수거하지 않습니다\.")
    matches = list(re.finditer(pattern, content, re.S))
    if len(matches) != 1:
        return None
    cells = matches[0].groupdict()
    monday, wednesday = (re.sub(r"\s+", "", cells[key]) for key in ('mon', 'wed'))
    if not balanced(monday) or not balanced(wednesday):
        return None
    # These delimiters distinguish the recycling lists from adjacent days.
    if (not monday.endswith(')') or '유색페트병' not in monday
            or not wednesday.endswith('일반쓰레기(불연성),소형폐가전')
            or '투명페트병' not in wednesday):
        return None
    monday = monday.removeprefix('재활용품(').removesuffix(')')
    wednesday = wednesday.removeprefix('재활용품(').replace('),일반쓰레기', ',일반쓰레기')
    groups = [
        ('월', monday), ('수', wednesday),
        ('화·목·일', '일반쓰레기(가연성)·음식물쓰레기'), ('금·토', '배출 금지'),
    ]
    requested = set(re.findall(r"([월화수목금토일])요일", query))
    if requested:
        groups = [(day, items) for days, items in groups for day in days.split('·') if day in requested]
    answer = '요일별 배출 품목은 다음과 같습니다.\n' + '\n'.join(
        f'- **{days}요일**: {items}.' for days, items in groups)
    return answer if len(answer) <= 480 else None


def _fresh(value: str | None) -> str | None:
    try:
        checked = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        if checked >= datetime.now(timezone.utc) - timedelta(days=SOURCE_DYNAMIC_MAX_AGE_DAYS):
            return checked.date().isoformat()
    except (TypeError, ValueError):
        pass
    return None


def parse_birth_support(content: str) -> str | None:
    """Read the 2026 municipal/provincial cash rows, excluding first-meeting vouchers."""
    if "출산지원금(구비, 시비)" not in content or "출산지원금(장애인)" not in content:
        return None
    section = content.split("출산지원금(구비, 시비)", 1)[1].split("출산지원금(장애인)", 1)[0]
    municipal = re.search(r"사하구에 주민등록.{0,100}?26년 모든 출생아.{0,100}?첫째부터\s*([\d,]+)만원", section, re.S)
    provincial = re.search(r"부산시에 주민등록.{0,100}?26년 둘째이후 출생아.{0,100}?둘째이후\s*([\d,]+)만원", section, re.S)
    if not municipal or not provincial:
        return None
    return (
        f"2026년 출생아 기준, 사하구 구비 출산지원금은 첫째부터 **{municipal.group(1)}만원**"
        f"(현금 일시금)입니다. 부산시 시비 출산지원금은 둘째 이후 출생아에 "
        f"**{provincial.group(1)}만원**(현금 일시금)으로 안내되어 있습니다. "
        "시비 지원은 부모와 자녀의 부산시 주민등록·거주 등 추가 조건이 있으므로 "
        "신청 전에 공식 안내를 확인하세요."
    )


def parse_health_certificate_fee(content: str) -> str | None:
    """Read the health-certificate row from the current annual fee table."""
    if "2026년 제증명 수수료 내역" not in content:
        return None
    section = content.split("2026년 제증명 수수료 내역", 1)[1]
    match = re.search(
        r"건강진단결과서\s*\(구\s*보건증\)\s*([\d,]+원)\s*(\d+일)",
        section, re.S,
    )
    if not match:
        return None
    return (
        f"사하구보건소의 2026년 수수료 안내에 따르면 건강진단결과서(구 보건증) "
        f"발급 수수료는 **{match.group(1)}**, 처리기간은 **{match.group(2)}**"
        "(업무일 기준)입니다."
    )


def parse_kiosk_fee(content: str) -> str | None:
    # Keep the exception directly with the free-fee rule. Never infer a fee
    # from "발급가능" in the separate installation table.
    rule = re.search(r"수수료 지불 방법\s*:\s*무료\s*\(([^)]+)\)\s*"
                     r"단,\s*부동산등기부등본\s*([\d,]+원)\s*\(([^)]+)\)", content)
    if not rule:
        return None
    return (f"사하구 무인민원발급기 수수료는 **무료**({rule.group(1)})입니다. "
            f"다만 **부동산등기부등본은 {rule.group(2)}**이며, {rule.group(3)}합니다. "
            "설치장소별 운영시간과 발급 가능한 서류는 공식 안내에서 확인하세요.")


def parse_adult_passport_fee(content: str, query: str) -> str | None:
    if not any(word in query for word in ("성인", "어른", "18세이상")) or '10년' not in query:
        return None
    table = re.search(r"10년\s*58면\s*([\d,]+원)\s*만18세 이상\s*26면\s*([\d,]+원)", content)
    if not table:
        return None
    if '58면' in query:
        faces, price = '58면', table.group(1)
    elif '26면' in query:
        faces, price = '26면', table.group(2)
    else:
        return None
    return f"성인 **10년 복수여권 {faces}**의 발급 수수료는 **{price}**입니다."


def parse_bed_fee(content: str, query: str) -> str | None:
    """Use the total column only, and verify it equals collection + treatment."""
    if "수수료" not in content or "수집" not in content or "처리" not in content:
        return None
    size = '1인용' if '1인용' in query or '싱글' in query else '2인용' if any(word in query for word in ('2인용', '더블', '퀸', '킹')) else None
    kind = '돌침대' if '돌침대' in query else '일반침대' if '일반' in query and '침대' in query else None
    if '매트리스' in query and '침대' not in query:
        section = re.search(r"\n매트리스\n(.*?)\n전기매트\n", content, re.S)
        if not section or not size:
            return None
        kind = '라텍스' if '라텍스' in query else '일반'
        row = re.search(re.escape(kind + ' ' + size) + r"\s*([\d,]+)\s*([\d,]+)\s*([\d,]+)", section.group(1))
        if not row:
            return None
        total, collection, treatment = (int(value.replace(',', '')) for value in row.groups())
        if total != collection + treatment:
            return None
        return f"**{kind} 매트리스 {size}만** 배출하는 수수료는 **{total:,}원**입니다."
    if not size or not kind:
        return None
    row = re.search(re.escape(kind + ' ' + size) + r"\s*([\d,]+)\s*([\d,]+)\s*([\d,]+)", content)
    if not row:
        return None
    total, collection, treatment = (int(value.replace(',', '')) for value in row.groups())
    if total != collection + treatment:
        return None
    if not re.search(r"침대\s*\(매트리스, 서랍,\s*부속장치 포함\)", content):
        return None
    return (f"**{kind} {size}** 배출 수수료는 **{total:,}원**입니다. "
            "매트리스·서랍·부속장치를 포함한 침대 기준입니다.")


def answer_verified_table_question(query: str, client) -> dict | None:
    """Return None for other topics, or a sourced answer / safe abstention."""
    compact = re.sub(r"\s+", "", query or "")
    if "출산지원금" in compact and any(term in compact for term in ("얼마", "금액", "얼마나")):
        url, title, parser = _BIRTH_URL, "출산장려정책", parse_birth_support
    elif "보건증" in compact and any(term in compact for term in ("비용", "수수료", "얼마", "기간")):
        url, title, parser = _HEALTH_FEE_URL, "2026년도 각종검사 및 제증명 수수료 내역", parse_health_certificate_fee
    elif "무인민원발급기" in compact and any(term in compact for term in ("수수료", "비용", "얼마", "무료")):
        url, title, parser = _KIOSK_URL, "무인민원발급안내", parse_kiosk_fee
    elif "여권" in compact and any(term in compact for term in ("수수료", "비용", "얼마")):
        url, title, parser = _PASSPORT_URL, "여권발급안내", lambda body: parse_adult_passport_fee(body, compact)
    elif any(word in compact for word in ("침대", "매트리스")) and any(term in compact for term in ("수수료", "비용", "가격", "얼마")):
        url, title, parser = _WASTE_URL, "대형폐기물 수수료", lambda body: parse_bed_fee(body, compact)
    elif (any(word in compact for word in ("분리수거", "재활용", "분리배출", "쓰레기"))
          and any(word in compact for word in ("요일", "언제", "무슨날"))
          and not any(word in compact for word in ("대형폐기물", "사업장", "통계", "건수"))
          and ("요일" in compact or not any(word in compact for word in ("시간", "몇시", "시각")))):
        url, title, parser = _RECYCLING_URL, "생활쓰레기 배출요령", lambda body: parse_disposal_schedule(body, compact)
    else:
        return None

    years = re.findall(r"20\d{2}년", compact)
    if any(year != "2026년" for year in years):
        return {"answer": "질문하신 연도의 공식 표를 확인하지 못했습니다. 공식 안내 페이지를 확인해 주세요.",
                "sources": [], "verified": False}

    if url in (_BIRTH_URL, _HEALTH_FEE_URL, _KIOSK_URL) and "2026" not in compact and datetime.now(ZoneInfo("Asia/Seoul")).year != 2026:
        return {"answer": "현재 연도의 공식 수수료·지원금 표를 확인하지 못했습니다. 공식 안내 페이지를 확인해 주세요.",
                "sources": [], "verified": False}

    try:
        rows = client.table("raw_pages").select("content,last_checked_at").eq("url", url).limit(1).execute().data or []
    except Exception:
        rows = []
    checked_at = _fresh(rows[0].get("last_checked_at")) if rows else None
    answer = parser(rows[0].get("content") or "") if checked_at else None
    if not answer:
        detail = "요일별 배출 품목" if url == _RECYCLING_URL else "해당 금액과 기간"
        return {"answer": f"현재 공식 자료에서 {detail}을 확인하지 못했습니다. 공식 안내 페이지에서 확인해 주세요.",
                "sources": [], "verified": False}
    return {
        "answer": answer,
        "answer_details": "\n".join('> ' + line for line in rows[0]['content'].splitlines()) if url in (_WASTE_URL, _RECYCLING_URL) else "",
        "sources": [{
            "title": title, "url": url,
            "category": "환경/청소" if url in (_WASTE_URL, _RECYCLING_URL) else ("사하복지" if url == _BIRTH_URL else ("전자민원" if url in (_KIOSK_URL, _PASSPORT_URL) else "보건소")),
            "service_type": "환경" if url in (_WASTE_URL, _RECYCLING_URL) else ("복지" if url == _BIRTH_URL else ("민원" if url in (_KIOSK_URL, _PASSPORT_URL) else "보건")),
            "checked_at": checked_at, "source_type": "verified_page",
        }],
        "verified": True,
    }
