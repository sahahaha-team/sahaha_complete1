"""
Supabase DB - 원본 크롤링 데이터, 정제 청크, 대화 이력 저장
(MySQL 대신 Supabase PostgreSQL 사용)
"""

import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta

from config import SUPABASE_SERVICE_KEY
from database_db import get_supabase

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, admin: bool = None):
        """
        admin=None  : SUPABASE_SERVICE_KEY가 설정돼 있으면 admin, 아니면 anon
        admin=True  : service role 키 강제 사용 (RLS 우회)
        admin=False : anon 키 강제 사용 (RLS 적용)
        """
        if admin is None:
            admin = bool(SUPABASE_SERVICE_KEY)
        self.client = get_supabase(admin=admin)
        self._last_checked_supported = None
        self._ingestion_queue_supported = None

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
            "etag": getattr(page_data, "etag", None),
            "last_modified": getattr(page_data, "last_modified", None),
            "attachments": getattr(page_data, "attachments", None) or [],
        }).execute()
        return True

    def upsert_raw_page(self, page_data) -> str:
        content_hash = hashlib.md5(page_data.content.encode()).hexdigest()

        existing = self.client.table("raw_pages").select("id, content_hash, title, attachments").eq("url", page_data.url).execute()

        if not existing.data:
            self.client.table("raw_pages").insert({
                "url": page_data.url,
                "title": page_data.title,
                "content": page_data.content,
                "category": page_data.category,
                "sub_category": page_data.sub_category,
                "content_hash": content_hash,
                "etag": getattr(page_data, "etag", None),
                "last_modified": getattr(page_data, "last_modified", None),
                "attachments": getattr(page_data, "attachments", None) or [],
            }).execute()
            return "new"

        row = existing.data[0]
        attachments = getattr(page_data, 'attachments', None) or []
        if (row["content_hash"] == content_hash and row.get('title') == page_data.title
                and (row.get('attachments') or []) == attachments):
            # 본문과 첨부 링크가 모두 같을 때만 재처리를 생략한다.
            # 링크가 바뀌어도 get_text()의 본문 해시는 같을 수 있다.
            self._update_cache_validators_if_present(page_data)
            return "unchanged"

        self.client.table("raw_pages").update({
            "title": page_data.title,
            "content": page_data.content,
            "sub_category": page_data.sub_category,
            "content_hash": content_hash,
            "etag": getattr(page_data, "etag", None),
            "last_modified": getattr(page_data, "last_modified", None),
            "attachments": getattr(page_data, "attachments", None) or [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("url", page_data.url).execute()

        # 파생 청크/벡터는 새 버전의 처리와 임베딩이 성공한 뒤 정리한다.
        # 여기서 먼저 삭제하면 태깅 모델·임베딩 모델 장애 시 검색 가능한
        # 기존 데이터까지 사라질 수 있다.
        return "updated"

    def _update_cache_validators_if_present(self, page_data):
        """본문 미변경 시 etag/last_modified가 새로 들어왔다면 갱신"""
        etag = getattr(page_data, "etag", None)
        last_modified = getattr(page_data, "last_modified", None)
        if not (etag or last_modified):
            return
        try:
            self.client.table("raw_pages").update({
                "etag": etag,
                "last_modified": last_modified,
            }).eq("url", page_data.url).execute()
        except Exception as e:
            logger.warning(f"캐시 검증자 갱신 실패 ({page_data.url}): {e}")

    def mark_page_checked(self, url: str):
        """증분 회차에서 URL을 확인한 시각을 기록한다(구버전 스키마에서는 무시)."""
        if self._last_checked_supported is False:
            return
        try:
            self.client.table("raw_pages").update({
                "last_checked_at": datetime.now(timezone.utc).isoformat(),
            }).eq("url", url).execute()
            self._last_checked_supported = True
        except Exception as e:
            self._last_checked_supported = False
            logger.warning(f"last_checked_at 기록 비활성화(마이그레이션 필요): {e}")

    def start_crawl_run(self, mode: str = "incremental", menu: str = None):
        """크롤링 실행 감사 레코드를 만들고 ID를 반환한다."""
        try:
            result = self.client.table("crawl_runs").insert({
                "mode": mode,
                "menu": menu,
                "status": "running",
            }).execute()
            return result.data[0]["id"] if result.data else None
        except Exception as e:
            logger.warning(f"crawl_runs 시작 기록 생략(마이그레이션 필요): {e}")
            return None

    def finish_crawl_run(self, run_id, status: str, stats: dict, error_message: str = None):
        """크롤링 결과를 감사 레코드에 마감 기록한다."""
        if run_id is None:
            return
        try:
            self.client.table("crawl_runs").update({
                "status": status,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "new_count": int(stats.get("new", 0)),
                "updated_count": int(stats.get("updated", 0)),
                "unchanged_count": int(stats.get("unchanged", 0)),
                "deleted_count": int(stats.get("deleted", 0)),
                "error_message": (error_message or "")[:1000] or None,
            }).eq("id", run_id).execute()
        except Exception as e:
            logger.warning(f"crawl_runs 완료 기록 실패: {e}")

    def enqueue_ingestion_job(self, url: str, category: str = None):
        """변경 URL을 영속 작업 큐에 등록한다(마이그레이션 전에는 안전하게 생략)."""
        if self._ingestion_queue_supported is False:
            return None
        try:
            result = self.client.rpc("enqueue_ingestion_job", {
                "job_url": url,
                "job_category": category,
            }).execute()
            self._ingestion_queue_supported = True
            return result.data
        except Exception as e:
            self._ingestion_queue_supported = False
            logger.warning(f"ingestion_jobs 큐 비활성화(마이그레이션 필요): {e}")
            return None

    def update_ingestion_jobs(self, urls: list[str], status: str, error_message: str = None):
        if not urls or self._ingestion_queue_supported is False:
            return
        values = {
            "status": status,
            "error_message": (error_message or "")[:1000] or None,
        }
        now = datetime.now(timezone.utc).isoformat()
        if status == "running":
            values.update({"started_at": now, "finished_at": None})
        elif status in ("succeeded", "failed"):
            values["finished_at"] = now
        try:
            for offset in range(0, len(urls), 100):
                self.client.table("ingestion_jobs").update(values).in_(
                    "url", urls[offset:offset + 100]
                ).execute()
            self._ingestion_queue_supported = True
        except Exception as e:
            self._ingestion_queue_supported = False
            logger.warning(f"ingestion_jobs 상태 갱신 생략: {e}")

    def ingestion_queue_stats(self) -> dict:
        """관리 화면용 상태별 작업 수. 테이블 미적용 시 available=False."""
        try:
            rows = self.client.table("ingestion_jobs").select("status").range(0, 9999).execute().data or []
            counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0}
            for row in rows:
                status = row.get("status")
                if status in counts:
                    counts[status] += 1
            return {"available": True, **counts}
        except Exception:
            return {"available": False, "queued": 0, "running": 0, "succeeded": 0, "failed": 0}

    def latest_crawl_run(self) -> dict | None:
        try:
            rows = self.client.table("crawl_runs").select(
                "status,new_count,updated_count,unchanged_count,deleted_count,started_at,finished_at,error_message"
            ).order("started_at", desc=True).limit(1).execute().data or []
            return rows[0] if rows else None
        except Exception:
            return None

    def get_cache_validators(self) -> dict:
        """
        증분 크롤링용: 전체 URL의 캐시 검증자(+카테고리)를 dict로 반환.
        반환: {url: {"etag": str|None, "last_modified": str|None, "category": str}}
        """
        result = self.client.table("raw_pages") \
            .select("url, etag, last_modified, category") \
            .execute()
        out: dict = {}
        for r in result.data or []:
            out[r["url"]] = {
                "etag": r.get("etag"),
                "last_modified": r.get("last_modified"),
                "category": r.get("category"),
            }
        return out

    def get_all_urls(self) -> set:
        result = self.client.table("raw_pages").select("url").execute()
        return {r["url"] for r in result.data}

    def delete_page(self, url: str):
        self.client.table("processed_chunks").delete().eq("url", url).execute()
        self._delete_documents_by_url(url)
        self.client.table("raw_pages").delete().eq("url", url).execute()

    def _delete_documents_by_url(self, url: str):
        """원문 변경·삭제 시 이전 벡터가 검색 결과에 남지 않도록 제거한다."""
        try:
            self.client.table("documents").delete().eq("metadata->>url", url).execute()
        except Exception as e:
            # 구버전 PostgREST에서 JSON 경로 필터가 제한돼도 원문 처리는 계속한다.
            # 운영 점검 스크립트가 이후 stale document를 다시 정리한다.
            logger.warning(f"기존 벡터 삭제 실패 ({url}): {e}")

    def delete_stale_derived_for_urls(self, valid_chunk_ids_by_url: dict[str, set[str]]):
        """새 버전 저장 후 URL별로 더 이상 쓰이지 않는 청크/벡터만 제거한다."""
        for url, valid_ids in valid_chunk_ids_by_url.items():
            rows = self.client.table("processed_chunks").select("chunk_id").eq("url", url).execute().data or []
            stale_ids = [row["chunk_id"] for row in rows if row["chunk_id"] not in valid_ids]
            for offset in range(0, len(stale_ids), 100):
                batch = stale_ids[offset:offset + 100]
                if not batch:
                    continue
                self.client.table("processed_chunks").delete().in_("chunk_id", batch).execute()
                self.client.table("documents").delete().in_("id", batch).execute()

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
                # LLM이 본문에서 담당부서를 추출했을 때만 저장 (미명시 시 NULL)
                "department": metadata.get("department") or None,
                "target_audience": json.dumps(metadata.get("target_audience", []), ensure_ascii=False),
                "keywords": json.dumps(metadata.get("keywords", []), ensure_ascii=False),
                "has_deadline": metadata.get("has_deadline", False),
                "has_contact_info": metadata.get("has_contact_info", False),
                "summary": metadata.get("summary", ""),
                "attachments": getattr(chunk, "attachments", None) or [],
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

    def cleanup_old_conversations(self, ttl_days: int = 30) -> int:
        """TTL 경과 대화 이력 자동 삭제 (스케줄러에서 호출)"""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
        result = self.client.table("conversation_logs") \
            .delete() \
            .lt("created_at", cutoff) \
            .execute()
        count = len(result.data) if result.data else 0
        logger.info(f"대화 이력 정리: {ttl_days}일 경과 {count}건 삭제")
        return count

    def get_existing_chunk_ids(self, chunk_ids: list[str]) -> set[str]:
        """주어진 chunk_id 중 DB에 이미 존재하는 ID 반환 (중복 방지)"""
        if not chunk_ids:
            return set()
        existing = set()
        # Supabase in_ 쿼리는 길이 제한이 있으므로 100개 단위로 분할
        for i in range(0, len(chunk_ids), 100):
            batch = chunk_ids[i:i + 100]
            result = self.client.table("processed_chunks") \
                .select("chunk_id") \
                .in_("chunk_id", batch) \
                .execute()
            existing.update(r["chunk_id"] for r in result.data)
        return existing

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
