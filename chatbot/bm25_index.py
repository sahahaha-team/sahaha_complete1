"""
BM25 키워드 검색 인덱스
- kiwipiepy로 한국어 형태소 분석
- rank_bm25(Okapi BM25)로 점수 계산
- Supabase documents 테이블에서 문서를 로딩해 메모리 인덱스 구축 (싱글턴)
- 벡터 검색과 함께 하이브리드 검색에서 활용
"""

import os
import shutil
import logging
import threading
import time
from functools import lru_cache
from typing import Optional

from config import SUPABASE_SERVICE_KEY
from database_db import get_supabase

logger = logging.getLogger(__name__)


def page_sections_by_url(metadata_rows):
    sections, seen = {}, set()
    for meta in metadata_rows:
        url, heading, body = meta.get('url'), meta.get('section_heading'), meta.get('section_text')
        version = meta.get('content_hash')
        key = (url, heading, body, version)
        if not (url and heading and body) or key in seen:
            continue
        seen.add(key)
        sections.setdefault(url, []).append({'heading': heading, 'text': body, 'hash': version})
    return sections


def read_search_documents(client):
    """Stable primary-key pagination while the collector updates documents."""
    rows, after, page_size = [], None, 1000
    while True:
        query = client.table('documents').select('id, content, metadata').order('id').limit(page_size)
        if after is not None:
            query = query.gt('id', after)
        try:
            batch = query.execute().data or []
        except Exception as exc:
            if ('57014' in str(exc) or 'statement timeout' in str(exc).lower()) and page_size > 25:
                page_size = max(25, page_size // 2)
                continue
            raise
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        after = batch[-1]['id']

# 형태소 분석에서 제외할 품사 (조사, 어미 등 의미 없는 토큰)
EXCLUDED_POS_PREFIXES = ("J", "E", "X", "S")  # 조사/어미/접사/기호


def _init_kiwi():
    """
    Kiwi 초기화. 한글 사용자 경로(예: C:/Users/황상필/...) 환경에서
    기본 로딩이 segfault/Exception을 일으키는 문제를 회피하기 위해,
    항상 프로젝트 내 ASCII 경로(.kiwi_model)로 모델을 복사하여 사용.
    """
    from kiwipiepy import Kiwi

    proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dst = os.path.join(proj_root, ".kiwi_model")

    # ASCII 경로에 모델이 없으면 kiwipiepy_model에서 복사
    if not os.path.exists(os.path.join(dst, "extract.mdl")):
        try:
            import kiwipiepy_model
            src = os.path.dirname(kiwipiepy_model.__file__)
            os.makedirs(dst, exist_ok=True)
            for fname in os.listdir(src):
                full = os.path.join(src, fname)
                if os.path.isfile(full):
                    shutil.copy2(full, dst)
            logger.info(f"Kiwi 모델을 ASCII 경로로 복사: {dst}")
        except Exception as e:
            logger.error(f"Kiwi 모델 복사 실패: {e}")
            raise

    return Kiwi(model_path=dst)


class BM25Index:
    """Supabase documents 테이블 기반 BM25 인덱스 (싱글턴)"""

    _instance: Optional["BM25Index"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.kiwi = None
        self.bm25 = None
        self.doc_ids: list[str] = []
        self.doc_contents: list[str] = []
        self.doc_metadata: list[dict] = []
        self.enabled = False
        self.pages = None
        self._last_built = 0.0
        self._refresh_lock = threading.RLock()
        self._refresh_pending = False

        try:
            self.kiwi = _init_kiwi()
            logger.info("Kiwi 형태소 분석기 초기화 완료")
        except Exception as e:
            logger.warning(f"Kiwi 로딩 실패 - BM25 비활성화: {e}")
            self._initialized = True
            return

        self._build_from_supabase()
        self._initialized = True

    @lru_cache(maxsize=12000)
    def _tokenize(self, text: str) -> list[str]:
        """한국어 형태소 분석 → 의미 토큰만 반환 (조사·어미 제외)"""
        if not text or self.kiwi is None:
            return []
        tokens = self.kiwi.tokenize(text)
        return [
            tok.form for tok in tokens
            if not tok.tag.startswith(EXCLUDED_POS_PREFIXES) and len(tok.form) > 1
        ]

    def _build_from_supabase(self):
        """Supabase documents 테이블 전체 로딩 후 BM25 인덱스 구축"""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as e:
            logger.warning(f"rank_bm25 미설치 - BM25 비활성화: {e}")
            return

        try:
            admin = bool(SUPABASE_SERVICE_KEY)
            client = get_supabase(admin=admin)

            all_rows = read_search_documents(client)

            if not all_rows:
                logger.warning("BM25 인덱스: documents 테이블 비어있음")
                return

            logger.info(f"BM25 인덱스 구축 중 ({len(all_rows)}개 문서)...")
            tokenized_corpus = []
            title_tokens = {}
            for row in all_rows:
                self.doc_ids.append(row["id"])
                self.doc_contents.append(row.get("content", ""))
                meta = row.get("metadata") or {}
                if isinstance(meta, str):
                    import json
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                self.doc_metadata.append(meta)
                title = str(meta.get('title') or '')
                if title not in title_tokens:
                    title_tokens[title] = self._tokenize(title)
                tokenized_corpus.append(title_tokens[title] + self._tokenize(row.get("content", "")))

            self.bm25 = BM25Okapi(tokenized_corpus)
            from chatbot.page_index import OfficialPageIndex
            from database_db.database import Database
            sections_by_url = page_sections_by_url(self.doc_metadata)
            try:
                raw_rows = Database(admin=admin)._all_rows('raw_pages', 'url,title,content,category,attachments,last_checked_at')
                self.pages = OfficialPageIndex(raw_rows, sections_by_url, self._tokenize)
            except Exception as exc:
                logger.warning('원문 검색 인덱스 구축 실패; 청크 검색 유지: %s', type(exc).__name__)
                self.pages = None
            self.enabled = True
            self._last_built = time.monotonic()
            logger.info(f"BM25 인덱스 구축 완료: {len(all_rows)}개 문서")
        except Exception as e:
            logger.warning(f"BM25 인덱스 구축 실패: {e}")
            self.bm25 = None

    def search(self, query: str, top_n: int = 30) -> list[dict]:
        """
        BM25 검색.
        Returns:
            [{id, content, metadata, bm25_score}, ...] (점수 내림차순, 상위 top_n개)
        """
        if self.enabled and time.monotonic() - self._last_built > 300:
            self.rebuild()
        # Rebuild replaces both the scorer and row arrays. Read them as one
        # snapshot so a concurrent refresh cannot pair scores with other rows.
        with self._refresh_lock:
            return self._search_locked(query, top_n)

    def _search_locked(self, query: str, top_n: int) -> list[dict]:
        if not self.enabled or not self.bm25:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = self.bm25.get_scores(query_tokens)
        # 상위 top_n 인덱스 (np.argsort 회피, 단순 sorted 사용)
        indexed_scores = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )[:top_n]

        results = []
        for idx, score in indexed_scores:
            if score <= 0:
                continue
            results.append({
                "id": self.doc_ids[idx],
                "content": self.doc_contents[idx],
                "metadata": self.doc_metadata[idx],
                "bm25_score": float(score),
            })
        return results

    def rebuild(self):
        """Refresh off the request thread; publish a complete snapshot at once."""
        with self._refresh_lock:
            if self._refresh_pending or (self.enabled and time.monotonic() - self._last_built < 30):
                return
            self._refresh_pending = True
        def refresh():
            try:
                candidate = object.__new__(BM25Index)
                candidate.kiwi = self.kiwi
                candidate._tokenize = self._tokenize
                candidate.doc_ids, candidate.doc_contents, candidate.doc_metadata = [], [], []
                candidate.bm25, candidate.pages, candidate.enabled = None, None, False
                candidate._last_built = 0.0
                candidate._build_from_supabase()
                if candidate.enabled:
                    with self._refresh_lock:
                        for name in ('doc_ids', 'doc_contents', 'doc_metadata', 'bm25', 'pages', 'enabled', '_last_built'):
                            setattr(self, name, getattr(candidate, name))
                else:
                    self._last_built = time.monotonic()
            finally:
                with self._refresh_lock:
                    self._refresh_pending = False
        threading.Thread(target=refresh, name='official-search-refresh', daemon=True).start()

    def search_pages(self, query: str, keywords: set[str], top_n: int = 30) -> list[dict]:
        if self.enabled and time.monotonic() - self._last_built > 300:
            self.rebuild()
        with self._refresh_lock:
            return self.pages.search(query, keywords, top_n) if self.pages else []
