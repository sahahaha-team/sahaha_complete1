"""
ChromaDB 벡터 스토어 - HuggingFace 로컬 임베딩 사용 (완전 무료)
한국어 지원 모델: paraphrase-multilingual-MiniLM-L12-v2
"""

import json
import logging
import chromadb
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

from config import CHROMA_DB_PATH, CHROMA_COLLECTION

logger = logging.getLogger(__name__)

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class VectorStore:
    def __init__(self):
        logger.info(f"임베딩 모델 로딩 중: {EMBED_MODEL}")
        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBED_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self.client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        self.collection_name = CHROMA_COLLECTION
        logger.info(f"ChromaDB 초기화: {CHROMA_DB_PATH}")

    def _get_vectorstore(self) -> Chroma:
        return Chroma(
            client=self.client,
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
        )

    def add_chunks(self, chunks_with_meta: list, db=None) -> list[str]:
        """청크 임베딩 후 저장"""
        texts, metadatas, ids = [], [], []

        for chunk, metadata in chunks_with_meta:
            texts.append(chunk.content)
            ids.append(chunk.chunk_id)

            safe_meta = {}
            for k, v in metadata.items():
                if isinstance(v, list):
                    safe_meta[k] = json.dumps(v, ensure_ascii=False)
                elif isinstance(v, bool):
                    safe_meta[k] = str(v)
                else:
                    safe_meta[k] = str(v) if v is not None else ""
            metadatas.append(safe_meta)

        vectorstore = self._get_vectorstore()
        vectorstore.add_texts(texts=texts, metadatas=metadatas, ids=ids)

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
            logger.info(f"임베딩 진행: {min(i+batch_size, total)}/{total}")

    def similarity_search(self, query: str, k: int = 5, filter_meta: dict = None) -> list:
        """유사도 검색"""
        vectorstore = self._get_vectorstore()
        kwargs = {"k": k}
        if filter_meta:
            kwargs["filter"] = filter_meta
        return vectorstore.similarity_search(query, **kwargs)

    def collection_stats(self) -> dict:
        col = self.client.get_or_create_collection(self.collection_name)
        return {"total_vectors": col.count()}
