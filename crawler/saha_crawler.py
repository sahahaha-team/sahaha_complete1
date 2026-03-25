"""
사하구청 홈페이지 크롤러
- requests + BeautifulSoup 기반 크롤링
- 동적 페이지는 Selenium fallback
"""

import time
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, field
from typing import Optional
from fake_useragent import UserAgent

from config import BASE_URL, CRAWL_DELAY, REQUEST_TIMEOUT, MAX_RETRIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class PageData:
    url: str
    title: str
    content: str
    category: str
    sub_category: str = ""
    links: list = field(default_factory=list)
    raw_html: str = ""


class SahaCrawler:
    def __init__(self, use_selenium: bool = False):
        self.session = self._init_session()
        self.use_selenium = use_selenium
        self.driver = None
        if use_selenium:
            self._init_selenium()

    def _init_session(self) -> requests.Session:
        ua = UserAgent()
        session = requests.Session()
        session.headers.update({
            "User-Agent": ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": BASE_URL,
        })
        return session

    def _init_selenium(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(f"user-agent={UserAgent().random}")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        logger.info("Selenium 드라이버 초기화 완료")

    def fetch_page(self, url: str) -> Optional[str]:
        """페이지 HTML 가져오기 (requests → Selenium fallback)"""
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                resp.encoding = "utf-8"
                html = resp.text

                # JS 렌더링이 필요한 경우 감지
                if self.use_selenium and self._needs_js_rendering(html):
                    html = self._fetch_with_selenium(url)

                return html

            except requests.RequestException as e:
                logger.warning(f"요청 실패 ({attempt+1}/{MAX_RETRIES}) {url}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)

        return None

    def _needs_js_rendering(self, html: str) -> bool:
        """JS 렌더링 필요 여부 판단"""
        soup = BeautifulSoup(html, "lxml")
        body_text = soup.get_text(strip=True)
        return len(body_text) < 200

    def _fetch_with_selenium(self, url: str) -> str:
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By

        self.driver.get(url)
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            pass
        return self.driver.page_source

    def parse_page(self, html: str, url: str, category: str) -> PageData:
        """HTML 파싱 → PageData 추출"""
        soup = BeautifulSoup(html, "lxml")

        title = self._extract_title(soup)
        content = self._extract_content(soup)
        sub_category = self._extract_sub_category(soup)
        links = self._extract_links(soup, url)

        return PageData(
            url=url,
            title=title,
            content=content,
            category=category,
            sub_category=sub_category,
            links=links,
            raw_html=html,
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        for selector in ["h1.title", "h2.title", ".cont_title h2", ".sub_title h2", "title"]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(strip=True)
        return soup.title.get_text(strip=True) if soup.title else ""

    def _extract_content(self, soup: BeautifulSoup) -> str:
        # 불필요한 태그 제거
        for tag in soup.select("script, style, nav, header, footer, .gnb, .lnb, .side_menu, #footer"):
            tag.decompose()

        # 본문 영역 우선 추출
        for selector in [".cont_area", "#contents", ".content_area", ".board_view", "main", "article"]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(separator="\n", strip=True)

        return soup.get_text(separator="\n", strip=True)

    def _extract_sub_category(self, soup: BeautifulSoup) -> str:
        breadcrumb = soup.select_one(".breadcrumb, .location, #location")
        if breadcrumb:
            items = breadcrumb.get_text(separator=" > ", strip=True)
            return items
        return ""

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list:
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            # 사하구청 도메인 내부 링크만
            if "saha.go.kr" in parsed.netloc and parsed.scheme in ("http", "https"):
                links.append(full_url)
        return list(set(links))

    def crawl_menu(self, menu_name: str, start_url: str, max_pages: int = 50) -> list[PageData]:
        """메뉴 전체 크롤링"""
        results = []
        visited = set()
        queue = [start_url]

        logger.info(f"[{menu_name}] 크롤링 시작: {start_url}")

        while queue and len(results) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            html = self.fetch_page(url)
            if not html:
                continue

            page_data = self.parse_page(html, url, menu_name)
            if page_data.content:
                results.append(page_data)
                logger.info(f"  [{len(results)}/{max_pages}] {page_data.title[:40]} - {url}")

            # 하위 링크 큐 추가
            for link in page_data.links:
                if link not in visited and self._is_target_url(link):
                    queue.append(link)

            time.sleep(CRAWL_DELAY)

        logger.info(f"[{menu_name}] 완료: {len(results)}개 페이지 수집")
        return results

    def _is_target_url(self, url: str) -> bool:
        """크롤링 대상 URL 필터"""
        exclude_patterns = [
            ".pdf", ".hwp", ".xlsx", ".doc", ".zip",
            "javascript:", "mailto:", "#",
            "/english/", "/chinese/",
        ]
        return not any(p in url.lower() for p in exclude_patterns)

    def close(self):
        if self.driver:
            self.driver.quit()
