"""
사하구청 홈페이지 크롤러
- requests + BeautifulSoup 기반 크롤링
- 동적 페이지는 Selenium fallback
"""

import time
import logging
import requests
from bs4 import BeautifulSoup
from collections import deque
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
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
    # HTTP 캐시 검증자 (다음 증분 크롤링에서 If-None-Match / If-Modified-Since 헤더로 전송)
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    # 증분 크롤링 전용 상태 플래그 (run_incremental이 결과를 분기 처리하는 데 사용)
    #   not_modified : 304 응답으로 본문이 변경되지 않음 (title/content 비어있음)
    #   deleted      : 404 응답으로 페이지가 사라짐 (DB에서도 제거 필요)
    #   transient_fail: 일시 네트워크 오류 (보존, 다음 회차에 재시도)
    not_modified: bool = False
    deleted: bool = False
    transient_fail: bool = False


class SahaCrawler:
    def __init__(self, use_selenium: bool = False, respect_robots: bool = True):
        self.session = self._init_session()
        self.use_selenium = use_selenium
        self.driver = None
        self.user_agent = self.session.headers.get("User-Agent", "*")
        self.robot_parser = self._init_robots(respect_robots)
        # URL별 ETag/Last-Modified 캐시. 증분 크롤링에서 set_cache_validators()로
        # 주입하면 fetch_page가 자동으로 조건부 GET 헤더를 추가한다.
        self.cache_validators: dict = {}
        if use_selenium:
            self._init_selenium()

    def set_cache_validators(self, validators: dict):
        """
        증분 크롤링 시작 전에 호출하여 URL별 캐시 검증자를 주입.
        validators = {url: {"etag": str|None, "last_modified": str|None}}
        """
        self.cache_validators = validators or {}

    def _init_robots(self, respect_robots: bool) -> Optional[RobotFileParser]:
        """robots.txt 파싱 (실패 시 모든 URL 허용)"""
        if not respect_robots:
            return None
        rp = RobotFileParser()
        rp.set_url(urljoin(BASE_URL, "/robots.txt"))
        try:
            rp.read()
            logger.info(f"robots.txt 로딩 완료: {BASE_URL}/robots.txt")
            return rp
        except Exception as e:
            logger.warning(f"robots.txt 로딩 실패 (전체 허용으로 동작): {e}")
            return None

    def _can_fetch(self, url: str) -> bool:
        """robots.txt 정책 확인"""
        if self.robot_parser is None:
            return True
        try:
            return self.robot_parser.can_fetch(self.user_agent, url)
        except Exception:
            return True

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

    def fetch_page(self, url: str) -> Optional[dict]:
        """
        페이지 HTML 가져오기 (조건부 GET 지원).

        cache_validators에 해당 URL의 ETag/Last-Modified가 있으면
        If-None-Match / If-Modified-Since 헤더를 함께 전송한다.

        Returns:
            성공: {
                "html": str|None,            # 304일 때 None
                "etag": str|None,            # 새 ETag (304이면 캐시값 그대로)
                "last_modified": str|None,
                "status": "ok"|"not_modified"|"deleted",
            }
            실패: None (일시적 네트워크 오류 — 호출자는 "여전히 존재"로 추정)
        """
        cached = self.cache_validators.get(url, {})
        cond_headers = {}
        if cached.get("etag"):
            cond_headers["If-None-Match"] = cached["etag"]
        if cached.get("last_modified"):
            cond_headers["If-Modified-Since"] = cached["last_modified"]

        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT, headers=cond_headers)

                # 304 Not Modified: 본문 다운로드 없이 즉시 반환 (서버 부하 최소화)
                if resp.status_code == 304:
                    return {
                        "html": None,
                        "etag": cached.get("etag"),
                        "last_modified": cached.get("last_modified"),
                        "status": "not_modified",
                    }

                # 404: 페이지 삭제됨 (DB에서도 제거하도록 호출자에 알림)
                if resp.status_code == 404:
                    return {
                        "html": None,
                        "etag": None,
                        "last_modified": None,
                        "status": "deleted",
                    }

                resp.raise_for_status()
                resp.encoding = "utf-8"
                html = resp.text

                if self.use_selenium and self._needs_js_rendering(html):
                    html = self._fetch_with_selenium(url)

                return {
                    "html": html,
                    "etag": resp.headers.get("ETag"),
                    "last_modified": resp.headers.get("Last-Modified"),
                    "status": "ok",
                }

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

    def crawl_menu(
        self,
        menu_name: str,
        start_url: str,
        max_pages: int = 50,
        known_urls: Optional[list] = None,
    ) -> list[PageData]:
        """
        메뉴 BFS 크롤링.

        known_urls를 주면(증분 모드) start_url과 함께 시드 큐에 추가되어,
        landing 페이지가 304를 반환해도 알려진 URL은 빠짐없이 방문된다.

        max_pages는 BFS로 *새로 발견한* URL 수의 상한이며, known_urls는
        별도로 항상 시도한다(증분 회차마다 모든 기존 URL을 점검).

        반환되는 PageData는 다음 4종 중 하나:
          - 정상: content 채워짐
          - not_modified=True: 304 응답, 본문 없음
          - deleted=True: 404 응답, DB에서 제거 필요
          - transient_fail=True: 네트워크 오류 (보존)
        """
        results: list[PageData] = []
        visited: set[str] = set()
        queue: deque[str] = deque([start_url])
        known_set: set[str] = set(known_urls or [])
        if known_urls:
            queue.extend(u for u in known_urls if u != start_url)

        bfs_new_count = 0  # BFS로 새로 발견하여 처리한 페이지 수 (known과 별도 집계)

        incremental = bool(self.cache_validators or known_urls)
        mode = "증분" if incremental else "전수"
        logger.info(
            f"[{menu_name}] {mode} 크롤링 시작: {start_url} "
            f"(known={len(known_set)}, max_new={max_pages})"
        )

        while queue:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            is_known = url in known_set

            # BFS로 새로 발견한 URL만 max_pages 제한. known URL은 항상 처리.
            if not is_known and bfs_new_count >= max_pages:
                continue

            if not self._can_fetch(url):
                logger.info(f"  [SKIP-robots] {url}")
                continue

            fetch_result = self.fetch_page(url)
            if fetch_result is None:
                # 일시 실패 — 알려진 URL이면 보존 표시 (다음 회차 재시도)
                if is_known:
                    results.append(PageData(
                        url=url, title="", content="", category=menu_name,
                        transient_fail=True,
                    ))
                continue

            status = fetch_result["status"]

            if status == "not_modified":
                # 본문 없음 → 링크 추출 불가. 신규 URL은 listing 페이지가 갱신될 때
                # 함께 발견되므로 누락 위험은 낮음.
                results.append(PageData(
                    url=url, title="", content="", category=menu_name,
                    etag=fetch_result["etag"],
                    last_modified=fetch_result["last_modified"],
                    not_modified=True,
                ))
                continue

            if status == "deleted":
                results.append(PageData(
                    url=url, title="", content="", category=menu_name,
                    deleted=True,
                ))
                continue

            # status == "ok": 본문이 있으니 파싱
            html = fetch_result["html"]
            if not html:
                continue

            page_data = self.parse_page(html, url, menu_name)
            page_data.etag = fetch_result["etag"]
            page_data.last_modified = fetch_result["last_modified"]

            if page_data.content:
                results.append(page_data)
                if not is_known:
                    bfs_new_count += 1
                logger.info(
                    f"  [{bfs_new_count}/{max_pages} 신규+known] "
                    f"{page_data.title[:40]} - {url}"
                )

            for link in page_data.links:
                if link not in visited and self._is_target_url(link):
                    queue.append(link)

            time.sleep(CRAWL_DELAY)

        # 통계 로그
        n_ok = sum(1 for p in results if not (p.not_modified or p.deleted or p.transient_fail))
        n_304 = sum(1 for p in results if p.not_modified)
        n_404 = sum(1 for p in results if p.deleted)
        n_fail = sum(1 for p in results if p.transient_fail)
        logger.info(
            f"[{menu_name}] 완료: ok={n_ok}, 304={n_304}, 404={n_404}, 일시실패={n_fail}"
        )
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
