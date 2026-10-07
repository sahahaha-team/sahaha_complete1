"""Build the local, official department/duty/phone directory (no LLM).

python scripts/build_contact_directory.py
python scripts/build_contact_directory.py --refresh
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PHONE_URL = "https://www.saha.go.kr/portal/contents.do?mId=0604060000"
OUTPUT_PATH = ROOT / "data" / "department_contacts.json"


def format_staff_phone(raw: str, area_code: str) -> str:
    if re.fullmatch(r"051-\d{3,4}-\d{4}(?:~\d{1,4})?", raw):
        return raw
    if re.fullmatch(r"051[\s()-]*\d{3}[\s-]*\d{4}", raw):
        digits = re.sub(r"\D", "", raw)
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    # The official Saha-gu phone guide establishes the 051 area code.
    if re.fullmatch(r"220[\s-]*\d{4}", raw) and area_code == "051":
        digits = re.sub(r"\D", "", raw)
        return f"{area_code}-{digits[:3]}-{digits[3:]}"
    return raw


def compact(text: str) -> str:
    return re.sub(r"[^가-힣a-z0-9]", "", text.lower())


def parse_representatives(html: str) -> dict[str, str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    phones = {}
    for table in soup.find_all("table"):
        caption = table.find("caption")
        if not caption or "대표 전화번호" not in caption.get_text(" ", strip=True):
            continue
        for row in table.select("tbody tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            # Each group is department / representative phone / fax.
            for offset in range(0, len(cells) - 2, 3):
                name, phone = cells[offset:offset + 2]
                if name and re.fullmatch(r"051-220-\d{4}(?:~\d{1,4})?", phone):
                    phones[name] = phone
    if len(phones) < 30:
        raise ValueError("공식 대표전화 표를 확인하지 못했습니다. 기존 파일을 유지합니다.")
    return phones


def atomic_save(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_contact_directory(staff: dict | None = None, *, phone_html: Path | None = None,
                            output: Path = OUTPUT_PATH) -> dict:
    if staff is None:
        staff = json.loads((ROOT / "data" / "staff_directory.json").read_text(encoding="utf-8"))
    if not staff.get("rows") or not staff.get("generated_at"):
        raise ValueError("공식 직원업무안내 자료가 없습니다.")

    if phone_html:
        html = phone_html.read_text(encoding="utf-8")
        representative_checked = datetime.fromtimestamp(phone_html.stat().st_mtime, timezone.utc)
    else:
        import requests
        response = requests.get(PHONE_URL, timeout=30)
        response.raise_for_status()
        response.encoding = "utf-8"
        html = response.text
        representative_checked = datetime.now(timezone.utc)
    representatives = parse_representatives(html)
    from bs4 import BeautifulSoup
    phone_text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    general_match = re.search(r"대표\s*전화(?:번호)?\s*[:：]?\s*(051-220-\d{4})", phone_text)
    if not general_match:
        raise ValueError("사하구청 대표전화 표를 확인하지 못했습니다. 기존 파일을 유지합니다.")

    # Morphology is computed once during the build, never on a chat request.
    from chatbot.bm25_index import _init_kiwi
    kiwi = _init_kiwi()
    departments = {name: {"name": name, "representative_phone": phone, "contacts": []}
                   for name, phone in representatives.items()}
    seen = set()
    for row in staff["rows"]:
        name = str(row.get("department", "")).strip()
        title = str(row.get("title", "")).strip()
        phone_raw = str(row.get("phone", "")).strip()
        phone = format_staff_phone(phone_raw, general_match.group(1).split("-")[0])
        duties = str(row.get("duties", "")).strip()
        key = (name, title, phone, duties)
        if not name or key in seen:
            continue
        seen.add(key)
        record = departments.setdefault(name, {"name": name, "representative_phone": "", "contacts": []})
        tokens = kiwi.tokenize(title + " " + duties)
        keywords = set()
        for index, token in enumerate(tokens):
            if token.tag.startswith(("NN", "SL")):
                term = compact(token.form)
                if len(term) >= 2:
                    keywords.add(term)
                if index and tokens[index - 1].tag.startswith(("NN", "SL")):
                    keywords.add(compact(tokens[index - 1].form + token.form))
        record["contacts"].append({
            "title": title, "phone": phone, "phone_raw": phone_raw, "duties": duties,
            "keywords": sorted(k for k in keywords if len(k) >= 2),
            "page": row.get("page", 1),
        })

    data = {
        "schema_version": 1,
        "staff_checked_at": staff["generated_at"],
        "staff_source_url": staff["source_url"],
        "representative_checked_at": representative_checked.isoformat(),
        "representative_source_url": PHONE_URL,
        "organization_phone": general_match.group(1),
        "departments": sorted(departments.values(), key=lambda item: item["name"]),
    }
    atomic_save(data, output)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="공식 직원업무안내도 새로 크롤링")
    parser.add_argument("--phone-html", type=Path, help="이미 내려받은 공식 대표전화 HTML")
    args = parser.parse_args()
    staff = None
    if args.refresh:
        from crawler.staff_directory import refresh_directory
        staff = refresh_directory(ROOT / "data" / "staff_directory.json")
    data = build_contact_directory(staff, phone_html=args.phone_html)
    print(f"저장: {OUTPUT_PATH}")
    print(f"부서 {len(data['departments'])}개 / 대표번호 "
          f"{sum(bool(d['representative_phone']) for d in data['departments'])}개 / "
          f"업무 연락처 {sum(len(d['contacts']) for d in data['departments'])}건")


if __name__ == "__main__":
    main()
