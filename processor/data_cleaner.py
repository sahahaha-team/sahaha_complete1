"""
크롤링 데이터 정제 모듈
- 텍스트 클리닝
- 청크 분할
- 중복 제거
"""

import re
import logging
import hashlib
from dataclasses import dataclass, field
from urllib.parse import urlparse
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import CHUNK_SIZE, CHUNK_OVERLAP
from chatbot.dept_directory import extract_explicit_department

logger = logging.getLogger(__name__)

_NON_PAGE_EXTENSIONS = (
    ".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".zip", ".txt", ".csv", ".jpg", ".jpeg",
    ".png", ".gif", ".webp", ".svg", ".ai",
)


def is_non_page_url(url: str) -> bool:
    """파일 다운로드·이미지 URL을 검색 본문으로 처리하지 않는다."""
    path = urlparse(url or "").path.lower()
    return (
        "/filedown" in path
        or "/cmm/fms/" in path
        or "/images/" in path
        or path.endswith(_NON_PAGE_EXTENSIONS)
    )


@dataclass
class CleanedChunk:
    chunk_id: str
    url: str
    title: str
    content: str
    category: str
    sub_category: str
    chunk_index: int
    total_chunks: int
    department_hint: str = ""
    # 페이지 첨부파일 목록 [{"name","url"}] — 같은 페이지의 모든 청크가 공유
    attachments: list = field(default_factory=list)


class DataCleaner:
    def __init__(self, db=None):
        """
        db: Database 인스턴스를 전달하면 DB의 기존 chunk_id를 미리 조회해
        재실행 시에도 중복 청크의 임베딩 비용을 줄임.
        """
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        self._seen_hashes: set = set()
        self._existing_chunk_ids: set = set()
        if db is not None:
            try:
                # 처음 1회만 DB에서 기존 chunk_id 전수 조회 (incremental 재실행 시 효율적)
                result = db.client.table("processed_chunks").select("chunk_id").execute()
                self._existing_chunk_ids = {r["chunk_id"] for r in (result.data or [])}
                logger.info(f"기존 chunk_id 캐시 로드: {len(self._existing_chunk_ids)}개")
            except Exception as e:
                logger.warning(f"기존 chunk_id 조회 실패 (메모리 중복만 감지): {e}")

    def clean_text(self, text: str) -> str:
        """텍스트 정제"""
        # 연속 공백/줄바꿈 정리
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)

        # 특수문자 정리 (한글, 영문, 숫자, 기본 문장부호 유지)
        # 구조화 파서가 만든 제목(#), 표(|), 문서 경로(>) 표시는 유지한다.
        text = re.sub(r"[^\w\s가-힣.,!?;:()\-\[\]\"\'%/#|>~]", " ", text)

        # 반복 문자 제거
        text = re.sub(r"(.)\1{4,}", r"\1\1", text)

        # 메뉴/네비게이션 잔재 제거
        nav_patterns = [
            r"홈\s*>\s*", r"home\s*>\s*",
            r"처음으로\s*", r"사이트맵\s*",
            r"글자크기\s*[가-힣]*\s*",
            r"인쇄\s*", r"공유\s*",
        ]
        for pattern in nav_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        return text.strip()

    def is_duplicate(self, content: str) -> bool:
        """중복 콘텐츠 확인"""
        h = hashlib.md5(content.encode()).hexdigest()
        if h in self._seen_hashes:
            return True
        self._seen_hashes.add(h)
        return False

    def is_valid_content(self, content: str) -> bool:
        """유효한 콘텐츠 여부 확인"""
        if not content or len(content) < 50:
            return False
        # 한글 포함 비율 확인 (행정 정보는 한글이 주)
        korean_chars = len(re.findall(r"[가-힣]", content))
        if korean_chars < 10:
            return False
        return True

    def split_structured_text(self, text: str) -> list[str]:
        """HTML에서 보존한 제목 경계를 따라 나누고, 큰 섹션만 글자 단위로 분할한다."""
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        if not any(re.match(r"^#{1,6}\s+", line) for line in lines):
            return self.splitter.split_text(text)

        heading_stack: list[str] = []
        sections: list[tuple[str, str]] = []
        body: list[str] = []

        def flush() -> None:
            if not body:
                return
            path = " > ".join(heading_stack)
            sections.append((path, "\n".join(body).strip()))
            body.clear()

        for line in lines:
            match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if not match:
                body.append(line)
                continue
            flush()
            level = len(match.group(1))
            heading = match.group(2).strip()
            heading_stack[:] = heading_stack[:level - 1]
            heading_stack.append(heading)
        flush()

        chunks: list[str] = []
        for path, section_body in sections:
            prefix = f"문서 위치: {path}\n" if path else ""
            available = max(120, CHUNK_SIZE - len(prefix))
            local_splitter = RecursiveCharacterTextSplitter(
                chunk_size=available,
                chunk_overlap=min(CHUNK_OVERLAP, max(0, available // 5)),
                separators=["\n표 | ", "\n- ", "\n", ". ", " ", ""],
            )
            pieces = local_splitter.split_text(section_body)
            chunks.extend((prefix + piece).strip() for piece in pieces if piece.strip())
        return chunks or self.splitter.split_text(text)

    def process(self, page_data) -> list[CleanedChunk]:
        """PageData → CleanedChunk 리스트 변환"""
        if is_non_page_url(getattr(page_data, "url", "")):
            logger.info(f"  비페이지 URL 제외: {page_data.url}")
            return []
        text = page_data.content
        if getattr(page_data, 'raw_html', ''):
            from bs4 import BeautifulSoup
            from crawler.saha_crawler import SahaCrawler
            crawler = object.__new__(SahaCrawler)
            text = crawler._extract_content(BeautifulSoup(page_data.raw_html, 'lxml'), page_data.url)
        cleaned = self.clean_text(text)

        if not self.is_valid_content(cleaned):
            return []
        if self.is_duplicate(cleaned):
            return []

        chunks = self.split_structured_text(cleaned)
        result = []
        skipped = 0
        attachments = getattr(page_data, "attachments", None) or []
        department_hint = extract_explicit_department(cleaned)

        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{page_data.url}_{i}".encode()).hexdigest()

            # DB에 이미 존재하는 chunk_id는 스킵 (재실행 비용 절감)
            if chunk_id in self._existing_chunk_ids:
                skipped += 1
                continue

            result.append(CleanedChunk(
                chunk_id=chunk_id,
                url=page_data.url,
                title=page_data.title,
                content=chunk,
                category=page_data.category,
                sub_category=page_data.sub_category,
                chunk_index=i,
                total_chunks=len(chunks),
                department_hint=department_hint,
                attachments=attachments,
            ))

        if skipped:
            logger.info(f"  중복 청크 스킵: {skipped}/{len(chunks)} ({page_data.url})")

        return result
