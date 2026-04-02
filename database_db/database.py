"""
Supabase DB - 원본 크롤링 데이터, 정제 청크, 대화 이력 저장
(MySQL 대신 Supabase PostgreSQL 사용)
"""

import json
import hashlib
import logging
from datetime import datetime, timezone

from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY를 .env에 설정해주세요")
        self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info(f"Supabase DB 연결: {SUPABASE_URL}")

    # ===== 크롤링 데이터 =====

    def save_raw_page(self, page_data) -> bool:
        content_hash = hashlib.md5(page_data.content.encode()).hexdigest()

        existing = self.client.table("raw_pages").select("id").eq("url", page_data.url).execute()
        if existing.data:
            return False

        self.client.table("raw_pages").insert({
            "url": page_data.url,
            "title": page_data.title,
            "content": page_data.content,
            "category": page_data.category,
            "sub_category": page_data.sub_category,
            "content_hash": content_hash,
        }).execute()
        return True

    def upsert_raw_page(self, page_data) -> str:
        content_hash = hashlib.md5(page_data.content.encode()).hexdigest()

        existing = self.client.table("raw_pages").select("id, content_hash").eq("url", page_data.url).execute()

        if not existing.data:
            self.client.table("raw_pages").insert({
                "url": page_data.url,
                "title": page_data.title,
                "content": page_data.content,
                "category": page_data.category,
                "sub_category": page_data.sub_category,
                "content_hash": content_hash,
            }).execute()
            return "new"

        row = existing.data[0]
        if row["content_hash"] == content_hash:
            return "unchanged"

        self.client.table("raw_pages").update({
            "title": page_data.title,
            "content": page_data.content,
            "sub_category": page_data.sub_category,
            "content_hash": content_hash,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("url", page_data.url).execute()

        # 해당 URL의 기존 청크 삭제
        self.client.table("processed_chunks").delete().eq("url", page_data.url).execute()
        return "updated"

    def get_all_urls(self) -> set:
        result = self.client.table("raw_pages").select("url").execute()
        return {r["url"] for r in result.data}

    def delete_page(self, url: str):
        self.client.table("processed_chunks").delete().eq("url", url).execute()
        self.client.table("raw_pages").delete().eq("url", url).execute()

    def get_pages_by_urls(self, urls: list) -> list:
        if not urls:
            return []
        result = self.client.table("raw_pages").select("*").in_("url", urls).execute()
        # 딕셔너리를 객체처럼 접근할 수 있도록 변환
        pages = []
        for r in result.data:
            pages.append(_DictObj(r))
        return pages

    def get_all_raw_pages(self) -> list:
        result = self.client.table("raw_pages").select("*").execute()
        return [_DictObj(r) for r in result.data]

    # ===== 청크 데이터 =====

    def save_chunks_bulk(self, tagged_chunks: list):
        rows = []
        for chunk, metadata in tagged_chunks:
            rows.append({
                "chunk_id": chunk.chunk_id,
                "url": chunk.url,
                "title": chunk.title,
                "content": chunk.content,
                "category": chunk.category,
                "sub_category": chunk.sub_category,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "service_type": metadata.get("service_type", "기타"),
                "target_audience": json.dumps(metadata.get("target_audience", []), ensure_ascii=False),
                "keywords": json.dumps(metadata.get("keywords", []), ensure_ascii=False),
                "has_deadline": metadata.get("has_deadline", False),
                "has_contact_info": metadata.get("has_contact_info", False),
                "summary": metadata.get("summary", ""),
            })

        # 배치 upsert (chunk_id 기준)
        for i in range(0, len(rows), 50):
            batch = rows[i:i + 50]
            self.client.table("processed_chunks").upsert(batch, on_conflict="chunk_id").execute()

        logger.info(f"DB 저장 완료: {len(rows)}개 청크")

    def get_unembedded_chunks(self) -> list:
        result = self.client.table("processed_chunks").select("*").eq("embedded", False).execute()
        return [_DictObj(r) for r in result.data]

    def mark_embedded(self, chunk_ids: list[str]):
        for i in range(0, len(chunk_ids), 50):
            batch = chunk_ids[i:i + 50]
            self.client.table("processed_chunks").update({"embedded": True}).in_("chunk_id", batch).execute()

    def get_chunks_by_metadata(self, category: str = None, service_type: str = None, limit: int = 100) -> list:
        query = self.client.table("processed_chunks").select("*")
        if category:
            query = query.eq("category", category)
        if service_type:
            query = query.eq("service_type", service_type)
        result = query.limit(limit).execute()
        return [_DictObj(r) for r in result.data]

    # ===== 대화 이력 =====

    def save_conversation(self, session_id: str, role: str, content: str, sources: str = None):
        self.client.table("conversation_logs").insert({
            "session_id": session_id,
            "role": role,
            "content": content,
            "sources": sources,
        }).execute()

    def get_conversation_history(self, session_id: str, limit: int = 10) -> list[dict]:
        result = self.client.table("conversation_logs") \
            .select("role, content, sources") \
            .eq("session_id", session_id) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()

        return list(reversed([
            {"role": r["role"], "content": r["content"], "sources": r["sources"]}
            for r in result.data
        ]))

    def clear_conversation(self, session_id: str):
        self.client.table("conversation_logs").delete().eq("session_id", session_id).execute()

    # ===== 통계 =====

    def stats(self) -> dict:
        raw = self.client.table("raw_pages").select("id", count="exact").execute()
        chunks = self.client.table("processed_chunks").select("chunk_id", count="exact").execute()
        embedded = self.client.table("processed_chunks").select("chunk_id", count="exact").eq("embedded", True).execute()
        convs = self.client.table("conversation_logs").select("id", count="exact").execute()
        return {
            "raw_pages": raw.count or 0,
            "chunks": chunks.count or 0,
            "embedded": embedded.count or 0,
            "conversations": convs.count or 0,
        }


class _DictObj:
    """딕셔너리를 객체 속성처럼 접근할 수 있게 하는 헬퍼"""
    def __init__(self, d: dict):
        self.__dict__.update(d)
