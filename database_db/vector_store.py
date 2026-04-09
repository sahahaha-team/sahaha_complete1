"""
Supabase pgvector 벡터 스토어 (무료 티어)
- HuggingFace 로컬 임베딩 (완전 무료)
- Supabase PostgreSQL + pgvector 확장으로 벡터 검색
"""

import json
import logging
import numpy as np
from supabase import create_client

from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384  # MiniLM-L12-v2 출력 차원


class VectorStore:
    def __init__(self):
        from langchain_community.embeddings import HuggingFaceEmbeddings

        logger.info(f"임베딩 모델 로딩 중: {EMBED_MODEL}")
        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBED_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY를 .env에 설정해주세요")

        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase 연결 완료")

        self._ensure_table()

    def _ensure_table(self):
        """Supabase에 벡터 테이블이 없으면 생성 안내 로그"""
        # Supabase SQL Editor에서 아래 SQL 실행 필요:
        # create extension if not exists vector;
        # create table if not exists documents (
        #   id text primary key,
        #   content text,
        #   embedding vector(384),
        #   metadata jsonb,
        #   created_at timestamp with time zone default now()
        # );
        # create index on documents using ivfflat (embedding vector_cosine_ops) with (lists = 100);
        #
        # -- 유사도 검색 함수
        # create or replace function match_documents(
        #   query_embedding vector(384),
        #   match_count int default 5,
        #   filter_metadata jsonb default '{}'
        # )
        # returns table (
        #   id text,
        #   content text,
        #   metadata jsonb,
        #   similarity float
        # )
        # language plpgsql
        # as $$
        # begin
        #   return query
        #   select
        #     d.id,
        #     d.content,
        #     d.metadata,
        #     1 - (d.embedding <=> query_embedding) as similarity
        #   from documents d
        #   where case
        #     when filter_metadata = '{}'::jsonb then true
        #     else d.metadata @> filter_metadata
        #   end
        #   order by d.embedding <=> query_embedding
        #   limit match_count;
        # end;
        # $$;
        logger.info("Supabase 벡터 테이블 준비 (SQL 설정 필요 - setup_supabase.sql 참조)")

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

        # Supabase upsert (배치)
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
        """Supabase 테이블에서 데이터를 가져와 Python에서 코사인 유사도 계산"""
        query_embedding = np.array(self.embed_text(query))

        # 테이블에서 전체 문서 조회
        result = self.supabase.table("documents").select("id, content, embedding, metadata").execute()

        docs = []
        for row in result.data:
            # 메타데이터 필터링
            if filter_meta:
                meta = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"])
                if not all(meta.get(fk) == fv for fk, fv in filter_meta.items()):
                    continue
            else:
                meta = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"])

            # 임베딩 파싱
            emb = row["embedding"]
            if isinstance(emb, str):
                emb = json.loads(emb)
            doc_embedding = np.array(emb)

            # 코사인 유사도 계산
            similarity = float(np.dot(query_embedding, doc_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding) + 1e-10
            ))

            # 최소 유사도 이상인 문서만 포함
            if similarity >= min_similarity:
                docs.append({
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": meta,
                    "similarity": similarity,
                })

        # 유사도 내림차순 정렬 후 상위 k개
        docs.sort(key=lambda x: x["similarity"], reverse=True)
        top = docs[:k]

        # 디버깅: 상위 결과 유사도 출력
        for d in top:
            title = d["metadata"].get("title", "?")[:30]
            logger.info(f"  [검색결과] 유사도={d['similarity']:.4f} | {title}")

        return top

    def hybrid_search(self, query: str, category: str = None, service_type: str = None, k: int = 5) -> list[dict]:
        """
        하이브리드 검색 (2단계 전략)
        1차: 메타데이터 필터링 (카테고리, 서비스 유형)
        2차: 필터된 범위 내 벡터 유사도 검색
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
