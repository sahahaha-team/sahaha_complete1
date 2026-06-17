"""Official Saha-gu staff directory crawler.

Fetches `https://www.saha.go.kr/portal/staff/list.do?mId=0604030000`
and builds a reusable department/contact/duty snapshot.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT, STAFF_DIRECTORY_URL

logger = logging.getLogger(__name__)

OUTPUT_PATH = Path("data/staff_directory.json")


@dataclass
class StaffRow:
    department: str
    title: str
    phone: str
    duties: str
    page: int


class StaffDirectoryCrawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9",
                "Referer": STAFF_DIRECTORY_URL,
            }
        )

    def fetch_page(self, page: int) -> str:
        response = self.session.post(
            STAFF_DIRECTORY_URL,
            data={"page": page, "deptCode": "", "searchType": "", "searchTxt": ""},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text

    def _extract_total_pages(self, soup: BeautifulSoup) -> int:
        text = soup.get_text(" ", strip=True)
        match = re.search(r"Page\s*\d+\s*/\s*(\d+)", text)
        if match:
            return int(match.group(1))

        page_links = []
        for anchor in soup.select(".paging a, .pagination a"):
            page_text = anchor.get_text(" ", strip=True)
            if page_text.isdigit():
                page_links.append(int(page_text))
        return max(page_links) if page_links else 1

    def parse_rows(self, html: str, page: int) -> list[StaffRow]:
        soup = BeautifulSoup(html, "lxml")
        table = soup.select_one("table.tableSt_list")
        if not table:
            return []

        rows: list[StaffRow] = []
        for tr in table.select("tbody tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 4:
                continue
            department, title, phone, duties = cells[:4]
            rows.append(
                StaffRow(
                    department=department.strip(),
                    title=title.strip(),
                    phone=phone.strip(),
                    duties=duties.strip(),
                    page=page,
                )
            )
        return rows

    def crawl(self) -> list[StaffRow]:
        first_html = self.fetch_page(1)
        first_soup = BeautifulSoup(first_html, "lxml")
        total_pages = self._extract_total_pages(first_soup)
        logger.info("Staff directory pages detected: %s", total_pages)

        all_rows = self.parse_rows(first_html, 1)
        for page in range(2, total_pages + 1):
            try:
                html = self.fetch_page(page)
                rows = self.parse_rows(html, page)
                if not rows:
                    logger.info("Stopping staff crawl at page %s because no rows were returned", page)
                    break
                all_rows.extend(rows)
            except Exception as exc:
                logger.warning("Failed to fetch staff directory page %s: %s", page, exc)
                break

        return all_rows


def build_directory(rows: list[StaffRow]) -> dict:
    departments: dict[str, dict] = defaultdict(
        lambda: {
            "name": "",
            "phone": "",
            "duties": [],
            "titles": [],
            "rows": [],
        }
    )

    for row in rows:
        dept = row.department.strip()
        if not dept:
            continue
        record = departments[dept]
        record["name"] = dept
        record["rows"].append(
            {
                "department": row.department,
                "title": row.title,
                "phone": row.phone,
                "duties": row.duties,
                "page": row.page,
            }
        )
        if row.title and row.title not in record["titles"]:
            record["titles"].append(row.title)
        if row.duties and row.duties not in record["duties"]:
            record["duties"].append(row.duties)
        if not record["phone"] or _is_better_phone_candidate(row.title, row.phone):
            record["phone"] = row.phone or record["phone"]

    department_list = []
    for dept, record in sorted(departments.items()):
        duties = " ".join(record["duties"])
        department_list.append(
            {
                "name": dept,
                "phone": record["phone"],
                "titles": record["titles"],
                "duty_summary": duties[:1000],
                "rows": record["rows"],
            }
        )

    return {
        "source_url": STAFF_DIRECTORY_URL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": [row.__dict__ for row in rows],
        "departments": department_list,
    }


def _is_better_phone_candidate(title: str, phone: str) -> bool:
    if not phone:
        return False
    priority = ["실장", "국장", "과장", "동장", "팀장", "계장", "담당", "주무관"]
    if any(token in title for token in priority[:4]):
        return True
    return any(token in title for token in priority)


def save_directory(data: dict, path: Path = OUTPUT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def refresh_directory(path: Path = OUTPUT_PATH) -> dict:
    crawler = StaffDirectoryCrawler()
    rows = crawler.crawl()
    data = build_directory(rows)
    save_directory(data, path)
    return data
