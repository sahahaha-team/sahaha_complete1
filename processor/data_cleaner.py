"""
크롤링 데이터 정제 모듈
- 텍스트 클리닝
- 청크 분할
- 중복 제거
"""

import re
import hashlib
from dataclasses import dataclass
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import CHUNK_SIZE, CHUNK_OVERLAP


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


class DataCleaner:
    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        self._seen_hashes: set = set()

    def clean_text(self, text: str) -> str:
        """텍스트 정제"""
        # 연속 공백/줄바꿈 정리
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)

        # 특수문자 정리 (한글, 영문, 숫자, 기본 문장부호 유지)
        text = re.sub(r"[^\w\s가-힣.,!?;:()\-\[\]\"\'%/]", " ", text)

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

    def process(self, page_data) -> list[CleanedChunk]:
        """PageData → CleanedChunk 리스트 변환"""
        cleaned = self.clean_text(page_data.content)

        if not self.is_valid_content(cleaned):
            return []
        if self.is_duplicate(cleaned):
            return []

        chunks = self.splitter.split_text(cleaned)
        result = []

        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{page_data.url}_{i}".encode()).hexdigest()
            result.append(CleanedChunk(
                chunk_id=chunk_id,
                url=page_data.url,
                title=page_data.title,
                content=chunk,
                category=page_data.category,
                sub_category=page_data.sub_category,
                chunk_index=i,
                total_chunks=len(chunks),
            ))

        return result
