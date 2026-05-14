"""
Supabase pgvector 벡터 스토어 (무료 티어)
- HuggingFace 로컬 임베딩 (완전 무료)
- Supabase match_documents() RPC로 서버사이드 pgvector 검색 수행
"""

import json
import logging

from config import SUPABASE_SERVICE_KEY
from database_db import get_supabase

logger = logging.getLogger(__name__)

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384  # MiniLM-L12-v2 출력 차원


class VectorStore:
    def __init__(self, admin: bool = None):
        # langchain-huggingface 우선, 미설치 시 langchain-community 폴백
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            from langchain_community.embeddings import HuggingFaceEmbeddings

        logger.info(f"임베딩 모델 로딩 중: {EMBED_MODEL}")
        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBED_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

        if admin is None:
            admin = bool(SUPABASE_SERVICE_KEY)
        self.supabase = get_supabase(admin=admin)
        logger.info("Supabase 벡터 스토어 준비 완료")

    def embed_text(self, text: str) -> list[float]:
        """텍스트 → 임베딩 벡터"""
        return self.embeddings.embed_query(text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """텍스트 배치 → 임베딩 벡터"""
        return self.embeddings.embed_documents(texts)

    def add_chunks(self, chunks_with_meta: list, db=None) -> list[str]:
        """청크 임베딩 후 Supabase에 저장"""
        texts = [chunk.content for chunk, _ in chunks_with_meta]
        ids = [chunk.chunk_id for chunk, _ in chunks_with_meta]

        embeddings = self.embed_texts(texts)

        rows = []
        for i, (chunk, metadata) in enumerate(chunks_with_meta):
            safe_meta = {}
            for k, v in metadata.items():
                if isinstance(v, bool):
                    safe_meta[k] = v
                elif isinstance(v, list):
                    safe_meta[k] = v
                elif v is not None:
                    safe_meta[k] = str(v)
                else:
                    safe_meta[k] = ""

            rows.append({
                "id": ids[i],
                "content": texts[i],
                "embedding": embeddings[i],
                "metadata": safe_meta,
            })

        self.supabase.table("documents").upsert(rows).execute()

        if db:
            db.mark_embedded([c.chunk_id for c, _ in chunks_with_meta])

        logger.info(f"벡터 저장 완료: {len(texts)}개")
        return ids

    def add_chunks_batch(self, chunks_with_meta: list, batch_size: int = 50, db=None):
        """배치 단위 임베딩 저장"""
        total = len(chunks_with_meta)
        for i in range(0, total, batch_size):
            batch = chunks_with_meta[i:i + batch_size]
            self.add_chunks(batch, db=db)
            logger.info(f"임베딩 진행: {min(i + batch_size, total)}/{total}")

    def similarity_search(self, query: str, k: int = 5, filter_meta: dict = None,
                          min_similarity: float = 0.5) -> list[dict]:
        """
        Supabase match_documents() RPC를 호출하여 서버사이드 pgvector 검색 수행.
        - 클라이언트는 query embedding만 전송 (전체 임베딩 노출 차단)
        - 서버에서 HNSW 인덱스로 유사도 계산 및 정렬
        """
        query_embedding = self.embed_text(query)
        try:
            result = self.supabase.rpc(
                "match_documents",
                {
                    "query_embedding": query_embedding,
                    "match_count": max(k * 2, 10),  # 임계값 필터 이후 k개 확보용 여유
                    "filter_metadata": filter_meta or {},
                },
            ).execute()
        except Exception as e:
            logger.error(f"match_documents RPC 호출 실패: {e}")
            return []

        docs = []
        for row in result.data or []:
            similarity = float(row.get("similarity", 0))
            if similarity < min_similarity:
                continue
            meta = row.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            docs.append({
                "id": row.get("id"),
                "content": row.get("content", ""),
                "metadata": meta,
                "similarity": similarity,
            })

        top = docs[:k]
        for d in top:
            title = (d["metadata"].get("title") or "?")[:30]
            logger.info(f"  [검색결과] 유사도={d['similarity']:.4f} | {title}")

        return top

    def hybrid_search(self, query: str, category: str = None, service_type: str = None, k: int = 5) -> list[dict]:
        """
        하이브리드 검색 (2단계 전략)
        1차: 메타데이터 필터 (카테고리, 서비스 유형)
        2차: 필터된 범위 내 pgvector 유사도 검색 (서버사이드)
        """
        filter_meta = {}
        if category:
            filter_meta["category"] = category
        if service_type:
            filter_meta["service_type"] = service_type

        return self.similarity_search(query, k=k, filter_meta=filter_meta if filter_meta else None)

    def collection_stats(self) -> dict:
        """벡터 DB 통계"""
        result = self.supabase.table("documents").select("id", count="exact").execute()
        return {"total_vectors": result.count or 0}
