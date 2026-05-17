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
from typing import Optional

from config import SUPABASE_SERVICE_KEY
from database_db import get_supabase

logger = logging.getLogger(__name__)

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

        try:
            self.kiwi = _init_kiwi()
            logger.info("Kiwi 형태소 분석기 초기화 완료")
        except Exception as e:
            logger.warning(f"Kiwi 로딩 실패 - BM25 비활성화: {e}")
            self._initialized = True
            return

        self._build_from_supabase()
        self._initialized = True

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

            # 페이지네이션 (Supabase 기본 1000건 제한)
            all_rows = []
            offset = 0
            page_size = 1000
            while True:
                result = client.table("documents") \
                    .select("id, content, metadata") \
                    .range(offset, offset + page_size - 1) \
                    .execute()
                rows = result.data or []
                if not rows:
                    break
                all_rows.extend(rows)
                if len(rows) < page_size:
                    break
                offset += page_size

            if not all_rows:
                logger.warning("BM25 인덱스: documents 테이블 비어있음")
                return

            logger.info(f"BM25 인덱스 구축 중 ({len(all_rows)}개 문서)...")
            tokenized_corpus = []
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
                tokenized_corpus.append(self._tokenize(row.get("content", "")))

            self.bm25 = BM25Okapi(tokenized_corpus)
            self.enabled = True
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
        """인덱스 재구축 (크롤링/임베딩 갱신 후 호출)"""
        self.doc_ids = []
        self.doc_contents = []
        self.doc_metadata = []
        self.bm25 = None
        self.enabled = False
        self._build_from_supabase()
