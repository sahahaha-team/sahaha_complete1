"""Search complete official crawler originals as well as embedding chunks."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from chatbot.answer_goal import answer_goal, GOAL_WORDS
from chatbot.evidence import is_official_document, is_answerable_document, topic_support, is_time_compatible, is_service_source
from chatbot.query_subject import compact
from chatbot.source_answers import strip_page_chrome
from config import SOURCE_MAX_AGE_DAYS, SOURCE_DYNAMIC_MAX_AGE_DAYS

logger = logging.getLogger(__name__)


def page_rank(query: str, document: dict, keywords: set[str]) -> tuple:
    meta = document.get("metadata") or {}
    title = compact(str(meta.get("title") or ""))
    body = compact(str(document.get("content") or ""))
    hits = sum(word in title for word in keywords)
    goal_words = GOAL_WORDS.get(answer_goal(query), ())
    goal_hits = sum(compact(word) in body for word in goal_words)
    # Prefer a field near the subject over many generic action words anywhere
    # in a long, unrelated multi-service page.
    source = str(document.get("content") or "")
    windows = [compact(source[start:start + 650]) for start in range(0, len(source), 300)]
    coherence = max((sum(word in window for word in keywords) / max(1, len(keywords))
        + .15 * sum(compact(word) in window for word in goal_words) for window in windows), default=0)
    return (hits / max(1, len(keywords)), coherence, goal_hits,
            float(document.get("bm25_score") or 0))


class CrawledPageIndex:
    def __init__(self, client):
        self.client = client
        self._lock = threading.RLock()
        self._pages = []
        self._loaded_at = None
        self._refreshing = False

    def _load_pages(self):
        pages = []
        try:
            for start in range(0, 100000, 1000):
                rows = self.client.table("raw_pages").select(
                    "url,title,content,category,last_checked_at,attachments"
                ).order("url").range(start, start + 999).execute().data or []
                pages.extend(rows)
                if len(rows) < 1000:
                    break
            with self._lock:
                self._pages = pages
            logger.info("크롤링 원문 검색 갱신: %s개 페이지", len(pages))
        except Exception:
            logger.warning("크롤링 원문 검색 갱신 실패")
        finally:
            with self._lock:
                self._loaded_at = time.monotonic()
                self._refreshing = False

    def _snapshot(self):
        with self._lock:
            if self._loaded_at is None:
                # Only the first load waits; subsequent refreshes leave the
                # previous snapshot available to concurrent consultations.
                self._load_pages()
            elif time.monotonic() - self._loaded_at >= 300 and not self._refreshing:
                self._refreshing = True
                threading.Thread(target=self._load_pages, daemon=True, name="page-refresh").start()
            return list(self._pages)

    def search(self, query: str, keywords: set[str], *, limit: int = 15, url: str | None = None) -> list[dict]:
        goal = answer_goal(query)
        dynamic = goal in ("hours", "location", "cost", "schedule", "eligibility") or any(
            word in query for word in ("올해", "현재", "최신", "오늘", "지금", "운영", "시간",
                "수수료", "비용", "금액", "요금", "지원금", "기준", "대상", "기간", "언제",
                "전화", "연락처", "담당", "주소", "위치", "얼마", "몇 시"))
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=SOURCE_DYNAMIC_MAX_AGE_DAYS if dynamic else SOURCE_MAX_AGE_DAYS)
        results = []
        if url:
            try:
                pages = self.client.table("raw_pages").select(
                    "url,title,content,category,last_checked_at,attachments"
                ).eq("url", url).limit(1).execute().data or []
            except Exception:
                logger.warning("공식 URL 원문 조회 실패")
                pages = []
        else:
            pages = self._snapshot()
        for page in pages:
            if url and page.get("url") != url:
                continue
            try:
                checked = datetime.fromisoformat(str(page.get("last_checked_at")).replace("Z", "+00:00"))
                if checked.tzinfo is None:
                    checked = checked.replace(tzinfo=timezone.utc)
                if checked < cutoff:
                    continue
            except (TypeError, ValueError):
                continue
            doc = {"id": "raw:" + str(page.get("url")),
                "content": strip_page_chrome(page.get("content") or ""),
                "metadata": {"url": page.get("url"), "title": page.get("title") or "",
                    "category": page.get("category") or "", "source_type": "crawled_page",
                    "attachments": page.get("attachments") or [], "checked_at": checked.date().isoformat()},
                "similarity": 0.0, "vector_similarity": 0.0, "bm25_score": 0.0}
            # Validate the actual body, never let a stale or misleading title
            # turn an unrelated original into evidence.
            body_doc = {"content": doc["content"], "metadata": {"url": page.get("url")}}
            if (is_official_document(doc) and is_answerable_document(query, doc)
                    and is_time_compatible(query, doc) and topic_support(body_doc, keywords)[0]
                    and is_service_source(query, doc, keywords)):
                results.append(doc)
        return sorted(results, key=lambda doc: page_rank(query, doc, keywords), reverse=True)[:limit]
