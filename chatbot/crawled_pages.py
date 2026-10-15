"""Search complete official crawler originals as well as embedding chunks."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from chatbot.answer_goal import answer_goal, requested_goals, GOAL_WORDS
from chatbot.evidence import is_official_document, is_answerable_document, topic_support, is_time_compatible, is_service_source
from chatbot.query_subject import compact
from chatbot.source_answers import strip_page_chrome
from config import SOURCE_MAX_AGE_DAYS, SOURCE_DYNAMIC_MAX_AGE_DAYS

logger = logging.getLogger(__name__)


def page_rank(query: str, document: dict, keywords: set[str]) -> tuple:
    meta = document.get("metadata") or {}
    title = compact(str(meta.get("title") or ""))
    source_heading = next((compact(line.lstrip('# ')) for line in str(document.get('content') or '').splitlines()
                           if line.startswith('## ')),title)
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
    from chatbot.vaccination import is_vaccination_query
    clinical = int(is_vaccination_query(query) and '접종' in title)
    primary_hits = sum(word in source_heading for word in keywords)
    from chatbot.structured_answers import scoped_units, field_matches
    units = scoped_units(query,source,keywords)
    fields = requested_goals(query)
    coverage = sum(any(field_matches(field,u,query) for u in units) for field in fields) / max(1,len(fields))
    return (clinical, coverage, primary_hits / max(1,len(keywords)), hits / max(1, len(keywords)), coherence, goal_hits,
            float(document.get("bm25_score") or 0))


class CrawledPageIndex:
    def __init__(self, client):
        self.client = client
        self._lock = threading.RLock()
        self._pages = []
        self._loaded_at = None
        self._refreshing = False
        self._retry_at = 0.0

    def _load_pages(self):
        pages = []
        try:
            # Full HTML is much larger than embedding chunks. Small pages keep
            # the initial request below PostgREST/network response limits.
            batch_size = 25
            for start in range(0, 100000, batch_size):
                from database_db.raw_pages import read_raw_pages
                rows = read_raw_pages(self.client,
                    "url,title,content,raw_html,category,last_checked_at,attachments",
                    order='url', offset=start, count=batch_size)
                # Parse once per refresh. Re-parsing every full HTML page for
                # every question thrashes the small HTML cache and adds seconds.
                from chatbot.official_content import official_html_text
                for row in rows:
                    if row.get('raw_html'):
                        row['content'] = official_html_text(row['raw_html']) or row.get('content') or ''
                    row.pop('raw_html',None)
                pages.extend(rows)
                if len(rows) < batch_size:
                    break
            with self._lock:
                self._pages = pages
                self._loaded_at = time.monotonic()
                self._retry_at = 0.0
            logger.info("크롤링 원문 검색 갱신: %s개 페이지", len(pages))
        except Exception as exc:
            # Do not mark an empty failed load as a fresh five-minute snapshot.
            # Keep a previously successful snapshot and retry soon.
            logger.warning("크롤링 원문 검색 갱신 실패 (%s)", type(exc).__name__)
            self._retry_at = time.monotonic() + 5
        finally:
            with self._lock:
                self._refreshing = False

    def _snapshot(self):
        with self._lock:
            if self._loaded_at is None and time.monotonic() >= self._retry_at:
                # Only the first load waits; subsequent refreshes leave the
                # previous snapshot available to concurrent consultations.
                self._load_pages()
            elif (self._loaded_at is not None and time.monotonic() >= self._retry_at
                  and time.monotonic() - self._loaded_at >= 300 and not self._refreshing):
                self._refreshing = True
                threading.Thread(target=self._load_pages, daemon=True, name="page-refresh").start()
            return list(self._pages)

    def search(self, query: str, keywords: set[str], *, limit: int = 15, url: str | None = None) -> list[dict]:
        goal = answer_goal(query)
        from chatbot.freshness import source_max_age_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=source_max_age_days(query))
        results = []
        if url:
            try:
                from database_db.raw_pages import read_raw_pages
                pages = read_raw_pages(self.client,
                    'url,title,content,raw_html,category,last_checked_at,attachments',url=url,limit=1)
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
                if checked < cutoff or checked > datetime.now(timezone.utc) + timedelta(minutes=5):
                    continue
            except (TypeError, ValueError):
                continue
            from chatbot.official_content import official_html_text
            body = official_html_text(page.get('raw_html') or '') or page.get('content') or ''
            doc = {"id": "raw:" + str(page.get("url")),
                "content": strip_page_chrome(body),
                "metadata": {"url": page.get("url"), "title": page.get("title") or "",
                    "category": page.get("category") or "", "source_type": "crawled_page",
                    "attachments": page.get("attachments") or [], "checked_at": checked.date().isoformat()},
                "similarity": 0.0, "vector_similarity": 0.0, "bm25_score": 0.0}
            if 'raw_html' in page:
                doc['_raw_page'] = page
            # Validate the actual body, never let a stale or misleading title
            # turn an unrelated original into evidence.
            body_doc = {"content": doc["content"], "metadata": {"url": page.get("url")}}
            if (is_official_document(doc) and is_answerable_document(query, doc)
                    and is_time_compatible(query, doc) and topic_support(body_doc, keywords)[0]
                    and is_service_source(query, doc, keywords)):
                results.append(doc)
        return sorted(results, key=lambda doc: page_rank(query, doc, keywords), reverse=True)[:limit]
