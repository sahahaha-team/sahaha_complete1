"""Resumable public-site discovery, attachment extraction and nightly indexing.

The SQLite frontier is a local journal, not a second answer database. Supabase
remains the source used by the web chatbot. Denied/unsupported resources remain
visible in the coverage report; an empty queue never means every site fact is known.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from crawler.saha_crawler import SahaCrawler
from crawler.site_scope import (SITE_SEEDS, RobotsRules, canonical_url, is_attachment,
                                official_host, site_category, skip_reason)

LOG = logging.getLogger(__name__)
STATE = Path("data/site_sync.sqlite3")
REPORT = Path("data/site_sync_report.json")
_request_lock = threading.Lock()
_next_request = 0.0


def now():
    return datetime.now(timezone.utc).isoformat()


def postgres_safe_text(value):
    """Remove unsupported text code points without changing factual values.

    Binary document extractors can leave NULs in text or nested JSON strings.
    PostgreSQL rejects these even though SQLite and JSON can preserve them.
    """
    if isinstance(value, str):
        return re.sub(r'[\x00\ud800-\udfff]', ' ', value)
    if isinstance(value, list):
        return [postgres_safe_text(item) for item in value]
    if isinstance(value, dict):
        return {postgres_safe_text(key): postgres_safe_text(item) for key, item in value.items()}
    return value


def normalize_resource(row):
    result = dict(row)
    for field in ('content', 'title'):
        if result.get(field) is not None:
            result[field] = postgres_safe_text(result[field])
    for field in ('sections', 'attachments'):
        if field in result:
            parsed = json.loads(result[field] or '[]')
            result[field] = json.dumps(postgres_safe_text(parsed), ensure_ascii=False)
    return result


def get_public(url, *, max_bytes=8_000_000, policy_for=None):
    """Rate-limited GET; never follow a redirect outside the official scope."""
    global _next_request
    for _ in range(8):
        if policy_for is not None:
            policy = policy_for(url)
            if policy is None or not policy.allowed(url):
                raise ValueError('robots_unavailable' if policy is None else 'robots_disallow')
        with _request_lock:
            time.sleep(max(0, _next_request - time.monotonic()))
            _next_request = time.monotonic() + 0.5
        response = requests.get(url, timeout=(8, 25), allow_redirects=False, stream=True,
                                headers={"User-Agent": "SahaKnowledgeBot/1.0"})
        if response.is_redirect:
            redirected = canonical_url(response.headers.get("Location", ""), url)
            response.close()
            if not redirected:
                raise ValueError("redirect_outside_official_scope")
            url = redirected
            continue
        body = bytearray()
        try:
            for part in response.iter_content(65536):
                body.extend(part)
                if len(body) > max_bytes:
                    raise ValueError("resource_too_large")
        finally:
            response.close()
        return response.status_code, dict(response.headers), bytes(body), url
    raise ValueError("redirect_loop")


class Frontier:
    def __init__(self, path=STATE):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS resources (
            url TEXT PRIMARY KEY, parent TEXT, kind TEXT, status TEXT DEFAULT 'pending',
            reason TEXT, title TEXT, content TEXT, attachments TEXT DEFAULT '[]',
            checked_at TEXT, indexed_at TEXT, indexed_hash TEXT, attempts INTEGER DEFAULT 0)""")
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(resources)')}
        if 'sections' not in columns:
            self.db.execute("ALTER TABLE resources ADD COLUMN sections TEXT DEFAULT '[]'")
        self.db.commit()

    def add(self, value, parent="", kind=None):
        url = canonical_url(value, parent or SITE_SEEDS[0])
        if not url:
            return
        kind = kind or ("attachment" if is_attachment(url) else "page")
        reason = skip_reason(url)
        self.db.execute("INSERT OR IGNORE INTO resources(url,parent,kind,status,reason) VALUES(?,?,?,?,?)",
                        (url, parent, kind, "excluded" if reason else "pending", reason))

    def rows(self, where, args=(), limit=None):
        sql = "SELECT * FROM resources WHERE " + where
        if limit:
            sql += " LIMIT " + str(int(limit))
        return list(self.db.execute(sql, args))

    def update(self, url, **values):
        self.db.execute("UPDATE resources SET " + ",".join(k + "=?" for k in values) + " WHERE url=?",
                        (*values.values(), url))

    def reset(self):
        # Revisit old and newly discovered URLs nightly. Failures are retained
        # and retried. No orphan deletion based on an interrupted traversal.
        self.db.execute("UPDATE resources SET status='pending',reason=NULL,attempts=0 WHERE status!='excluded'")
        self.db.commit()

    def report(self, **extra):
        counts = dict(self.db.execute("SELECT status,count(*) FROM resources GROUP BY status"))
        groups = [dict(r) for r in self.db.execute("""SELECT kind,status,count(*) AS count
                     FROM resources GROUP BY kind,status""")]
        gaps = [dict(r) for r in self.db.execute("""SELECT url,parent,kind,status,reason FROM resources
                    WHERE status NOT IN ('fetched','empty') ORDER BY status,url""")]
        pending_index = self.db.execute("""SELECT count(*) FROM resources WHERE status='fetched'
                    AND (indexed_at IS NULL OR indexed_at < checked_at)""").fetchone()[0]
        by_site = {}
        for row in self.db.execute("SELECT url,status,indexed_at FROM resources"):
            site = site_category(row["url"])
            group = by_site.setdefault(site, {"discovered": 0, "fetched": 0, "indexed": 0, "robots_blocked": 0})
            group["discovered"] += 1
            group["fetched"] += int(row["status"] == "fetched")
            group["indexed"] += int(bool(row["indexed_at"]))
            group["robots_blocked"] += int(row["status"] == "robots_blocked")
        result = {"reported_at": now(), "scope": "public saha.go.kr and linked official subdomains",
                  "complete_site_claim": False, "counts": counts, "by_kind": groups,
                  "by_site": by_site, "pending_index": pending_index, "gaps": gaps, **extra}
        temporary = REPORT.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(REPORT)
        return result


def extract_attachment(body, headers, url, cache_dir):
    disposition = headers.get("Content-Disposition", "")
    filename = disposition.split("filename=")[-1].strip('"\' ;') if "filename=" in disposition else urlsplit(url).path
    suffix = Path(filename).suffix.lower()
    if body.startswith(b"%PDF"):
        suffix = ".pdf"
    if body.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
        suffix = ".hwp" if suffix not in (".xls", ".doc", ".ppt") else suffix
    if headers.get("Content-Type", "").startswith("image/"):
        suffix = ".png"
    if body.startswith(b"PK"):
        import io, zipfile
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            names = archive.namelist()
            if any(n.startswith("Contents/section") for n in names): suffix = ".hwpx"
            elif "word/document.xml" in names: suffix = ".docx"
            elif "xl/workbook.xml" in names: suffix = ".xlsx"
    supported = {".pdf", ".hwp", ".hwpx", ".docx", ".xlsx", ".txt", ".csv", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
    if suffix not in supported:
        return "", "unsupported_format_or_image"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / (hashlib.sha256(url.encode()).hexdigest() + suffix)
    path.write_bytes(body)
    if suffix in (".pdf", ".hwp", ".hwpx"):
        from crawler.file_loader import extract_text
        text = extract_text(path)
        if suffix == ".pdf":
            from crawler.image_text import scanned_pdf_text
            text = scanned_pdf_text(path)
    elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        from crawler.image_text import ocr_image
        text = ocr_image(path)
        if text:
            text = '[이미지 문자 인식 자료: 오자 가능, 원문 확인 필요]\n' + text
    elif suffix == ".docx":
        from docx import Document
        doc = Document(path)
        text = "\n".join([p.text for p in doc.paragraphs] +
                         [" | ".join(c.text for c in row.cells) for table in doc.tables for row in table.rows])
    elif suffix == ".xlsx":
        from openpyxl import load_workbook
        book = load_workbook(path, read_only=True, data_only=True)
        try:
            text = "\n".join(sheet.title + "\n" + "\n".join(
                " | ".join(str(v) for v in row if v is not None) for row in sheet.values) for sheet in book)
        finally:
            book.close()
    else:
        for encoding in ("utf-8-sig", "cp949", "utf-16"):
            try:
                text = body.decode(encoding)
                break
            except UnicodeDecodeError:
                text = ""
    return text, None if len(text.strip()) >= 50 else "no_text_or_scanned_document"


def fetch_resource(row, policy_for=None):
    url = row["url"]
    try:
        # Images/audio/video remain in the inventory; do not download them as HTML.
        if is_attachment(url) and urlsplit(url).path.lower().endswith(
                (".svg", ".mp4", ".mp3", ".zip")):
            return {"status": "unsupported", "reason": "image_media_or_archive_requires_separate_extraction"}
        status, headers, body, final_url = get_public(url, max_bytes=25_000_000 if row["kind"] == "attachment" else 8_000_000,
                                                    policy_for=policy_for)
        if status in (404, 410):
            return {"status": "deleted", "reason": "http_" + str(status)}
        if status != 200:
            return {"status": "failed", "reason": "http_" + str(status)}
        content_type = headers.get("Content-Type", "").lower()
        if row["kind"] == "attachment" or ("html" not in content_type and any(
                t in content_type for t in ("pdf", "octet-stream", "officedocument", "hwp", "image/"))):
            text, reason = extract_attachment(body, headers, url, Path("data/site_attachments"))
            return {"status": "unsupported" if reason else "fetched", "reason": reason,
                    "title": row["title"] or Path(urlsplit(url).path).name or "첨부문서",
                    "content": text, "attachments": "[]", "checked_at": now(), "links": []}
        soup = BeautifulSoup(body.decode("utf-8", errors="replace"), "lxml")
        from crawler.page_sections import extract_sections
        sections = extract_sections(str(soup))
        if "xml" in content_type or soup.find("urlset") or soup.find("sitemapindex"):
            return {"status": "empty", "links": [n.get_text(strip=True) for n in soup.find_all("loc")]}
        crawler = object.__new__(SahaCrawler)
        links = crawler._extract_links(soup, final_url)
        attachments = crawler._extract_attachments(soup, final_url)
        content_node = soup.select_one('.cont_area, #contents, .content_area, .board_view, main, article')
        if content_node:
            for image in content_node.select('img[src]'):
                source = image['src']
                if re.search(r'(?:icon|ico_|logo|btn_|bg_|blank|loading)', source, re.I):
                    continue
                image_url = canonical_url(source, final_url)
                if image_url:
                    attachments.append({'url': image_url, 'name': image.get('alt') or '본문 이미지 (문자 인식)'})
        title = crawler._extract_title(soup)
        # A navigation heading such as '노인복지' omits the actual program.
        # Keep the official document title on every section's search metadata.
        if soup.title and soup.title.get_text(' ', strip=True):
            title = soup.title.get_text(' ', strip=True)
        # Discover pagination rendered as a simple goPage(2) handler. Do not
        # execute arbitrary site JavaScript or submit forms.
        from urllib.parse import parse_qsl, urlencode, urlunsplit
        p = urlsplit(final_url)
        for a in soup.select("a[onclick]"):
            match = re.fullmatch(r"(?:return\s+)?(?:goPage|fn_goPage|fn_page)\(['\"]?(\d+)['\"]?\);?", a["onclick"].strip())
            if match:
                query = dict(parse_qsl(p.query)); query["pageIndex"] = match[1]
                links.append(urlunsplit((p.scheme,p.netloc,p.path,urlencode(query),"")))
        text = crawler._extract_content(soup)
        return {"status": "fetched" if len(text.strip()) >= 50 else "empty", "title": title,
                "content": text, "attachments": json.dumps(attachments, ensure_ascii=False),
                "sections": json.dumps(sections, ensure_ascii=False),
                "checked_at": now(), "links": links + [a["url"] for a in attachments],
                "attachment_names": {a["url"]: a["name"] for a in attachments}}
    except Exception as exc:
        # Error classes are enough for retry/audit; never include auth headers.
        if isinstance(exc, ValueError) and str(exc) in ('robots_unavailable', 'robots_disallow'):
            return {'status': 'robots_blocked', 'reason': str(exc)}
        return {"status": "failed", "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__}


def index_fetched(frontier, *, batch_size=25):
    frontier.report(phase='indexing', indexed_this_run=0)
    import torch
    torch.set_num_threads(4)
    from database_db.database import Database
    from database_db.vector_store import VectorStore
    from processor.data_cleaner import DataCleaner, CleanedChunk
    from processor.metadata_defaults import fallback_keywords

    db, vs = Database(admin=True), VectorStore(admin=True)
    remote_urls = db.get_all_urls()
    indexed = 0
    while True:
        rows = frontier.rows("status='fetched' AND (indexed_at IS NULL OR indexed_at < checked_at)", limit=batch_size)
        if not rows:
            break
        raw_rows, pairs, tagged, unchanged, changed = [], [], [], [], []
        for row in rows:
            # Sanitize checkpoints too, so an old failed row can be resumed
            # without downloading it again. Hashes describe exactly what is saved.
            safe_row = normalize_resource(row)
            corrections = {key: safe_row[key] for key in ('content', 'title', 'sections', 'attachments')
                           if safe_row[key] != row[key]}
            if corrections:
                frontier.update(row['url'], **corrections)
            row = safe_row
            digest = hashlib.sha256(((row["title"] or '') + '\n' + row["content"] + row["sections"]).encode()).hexdigest()
            if digest == row["indexed_hash"] and row["url"] in remote_urls:
                unchanged.append(row["url"])
                continue
            cleaner = DataCleaner()
            content = cleaner.clean_text(row["content"])
            if not cleaner.is_valid_content(content):
                frontier.update(row["url"], status="empty", reason="no_valid_administrative_text")
                continue
            # Dedup within a page only. The same text at two official URLs
            # must retain both sources and must never erase one page's vectors.
            sections = json.loads(row['sections']) or [{'heading': row['title'], 'text': content}]
            chunks = [(section['heading'], section['text'], piece)
                      for section in sections for piece in cleaner.splitter.split_text(
                          section['heading'] + '\n' + cleaner.clean_text(section['text']))]
            category = site_category(row["url"])
            attachments = json.loads(row["attachments"])
            service = {"보건소": "보건", "사하복지": "복지", "전자민원": "민원",
                       "문화관광": "문화", "을숙도문화회관": "문화", "평생학습": "교육",
                       "하단도서관": "교육", "다대도서관": "교육"}.get(category, "기타")
            raw_rows.append({"url": row["url"], "title": row["title"], "content": row["content"],
                             "category": category, "sub_category": "공식 사이트 전체 탐색",
                             "content_hash": hashlib.md5(row["content"].encode()).hexdigest(),
                             "attachments": attachments, "last_checked_at": row["checked_at"],
                             "updated_at": now()})
            valid = set()
            for i, (heading, section_text, piece) in enumerate(chunks):
                cid = hashlib.md5(f"{row['url']}_{i}".encode()).hexdigest()
                valid.add(cid)
                chunk = CleanedChunk(cid, row["url"], row["title"], piece, category,
                                     "공식 사이트 전체 탐색", i, len(chunks), attachments=attachments)
                meta = {"url": row["url"], "title": row["title"], "category": category,
                        "service_type": service, "department": "", "keywords": fallback_keywords(piece, row["title"]),
                        "attachments": attachments,
                        "source_type": "official_ocr" if '[이미지 문자 인식 자료:' in row['content'] else "official_attachment" if row["kind"] == "attachment" else "verified_page",
                        "verified_at": row["checked_at"], "content_hash": hashlib.sha256(row['content'].encode()).hexdigest(),
                        "parent_url": row["parent"], "section_heading": heading,
                        "section_text": section_text if len(section_text) <= 6000 else ''}
                pairs.append((chunk, meta)); tagged.append((chunk, meta))
            changed.append((row["url"], digest, valid))
        try:
            if raw_rows:
                db.save_chunks_bulk(tagged)
                vs.add_chunks_batch(pairs, batch_size=25, db=db)
                db.delete_stale_derived_for_urls({url: ids for url, _, ids in changed})
                # Publish only after derived data is ready. Reindexing must
                # not make the last verified page disappear from live search.
                db.client.table("raw_pages").upsert(raw_rows, on_conflict="url").execute()
            confirmed = unchanged + [url for url, _, _ in changed]
            if confirmed:
                db.client.table("raw_pages").update({"last_checked_at": now()}).in_("url", confirmed).execute()
            for url, digest, _ in changed:
                frontier.update(url, indexed_at=now(), indexed_hash=digest)
                remote_urls.add(url)
            for url in unchanged:
                frontier.update(url, indexed_at=now())
            indexed += len(confirmed)
            frontier.db.commit()
            frontier.report(phase="indexing", indexed_this_run=indexed)
            LOG.info("INDEXED pages=%s batch_chunks=%s", indexed, len(pairs))
        except Exception:
            frontier.db.commit()
            frontier.report(phase="index_failed", indexed_this_run=indexed)
            raise
    return indexed


def run_site_sync(*, resume=False, discover_only=False, max_fetch=0):
    """No page-count limit by default. --max-fetch is explicit partial testing."""
    from database_db.database import Database
    from database_db import get_supabase
    # An OS file lock prevents initial and scheduled crawls from racing.
    import msvcrt
    STATE.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(STATE.with_suffix(".lock"), "a+b")
    lock_file.seek(0); lock_file.write(b"0"); lock_file.flush(); lock_file.seek(0)
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_file.close()
        LOG.warning("Site sync already running; skipped duplicate")
        return {"phase": "already_running"}
    frontier = Frontier()
    run_id = None
    db = Database(admin=True)
    stats = {"new": 0, "updated": 0, "unchanged": 0, "deleted": 0}
    try:
        if not resume:
            frontier.reset()
        else:
            frontier.db.execute("UPDATE resources SET status='pending',reason=NULL WHERE status='failed'")
        for url in SITE_SEEDS:
            frontier.add(url)
        # Existing official URLs remain reachable even when removed from a
        # navigation menu. They are deleted only after a confirmed HTTP 404/410.
        for url in db.get_all_urls():
            if canonical_url(url): frontier.add(url)
        frontier.db.commit()
        run_id = db.start_crawl_run(mode="site_sync", menu="all_official_sites")
        robots = {}
        robots_lock = threading.Lock()

        def policy_for(url):
            origin = 'https://' + urlsplit(url).netloc
            with robots_lock:
                if origin not in robots:
                    try:
                        status, _, body, _ = get_public(origin + '/robots.txt')
                        robots[origin] = RobotsRules(body.decode('utf-8-sig', errors='replace')) if status == 200 else RobotsRules('') if status == 404 else None
                    except Exception:
                        robots[origin] = None
                return robots[origin]

        fetched = 0
        indexed = 0
        if resume and not discover_only:
            # Flush the interrupted write before discovering hundreds more URLs.
            indexed += index_fetched(frontier)
        with ThreadPoolExecutor(max_workers=3) as pool:
            while not max_fetch or fetched < max_fetch:
                batch = frontier.rows("status='pending'", limit=min(12, max_fetch-fetched) if max_fetch else 12)
                if not batch: break
                permitted = []
                for row in batch:
                    origin = "https://" + urlsplit(row["url"]).netloc
                    if origin not in robots:
                        try:
                            status, _, body, _ = get_public(origin + "/robots.txt")
                            robots[origin] = RobotsRules(body.decode("utf-8-sig", errors="replace")) if status == 200 else RobotsRules("") if status == 404 else None
                            if status == 200:
                                for sitemap in re.findall(r"(?im)^sitemap:\s*(\S+)", body.decode("utf-8", errors="replace")):
                                    frontier.add(sitemap)
                        except Exception:
                            robots[origin] = None
                    policy = robots[origin]
                    if policy is None or not policy.allowed(row["url"]):
                        frontier.update(row["url"], status="robots_blocked", reason="robots_unavailable" if policy is None else "robots_disallow")
                    else:
                        permitted.append(dict(row))
                for row, result in zip(permitted, pool.map(lambda row: fetch_resource(row, policy_for), permitted)):
                    result = normalize_resource(result)
                    links = result.pop("links", [])
                    names = result.pop("attachment_names", {})
                    result["attempts"] = row["attempts"] + 1
                    frontier.update(row["url"], **result)
                    for link in links:
                        frontier.add(link, row["url"])
                        normalized = canonical_url(link, row["url"])
                        if normalized and link in names:
                            frontier.db.execute("UPDATE resources SET title=COALESCE(title,?) WHERE url=?", (names[link], normalized))
                    if result["status"] == "deleted":
                        db.delete_page(row["url"]); stats["deleted"] += 1
                    fetched += 1
                frontier.db.commit()
                report = frontier.report(phase="discovering", fetched_this_run=fetched)
                LOG.info("CRAWL fetched=%s counts=%s", fetched, report["counts"])
                if not discover_only and fetched and fetched // 200 > (fetched-len(permitted)) // 200:
                    indexed += index_fetched(frontier)
        indexed += 0 if discover_only else index_fetched(frontier)
        pending = len(frontier.rows("status='pending'"))
        report = frontier.report(phase="partial" if pending else "finished",
                                 fetched_this_run=fetched, indexed_this_run=indexed)
        stats["updated"] = indexed
        failures = report["counts"].get("failed", 0)
        db.finish_crawl_run(run_id, "failed" if failures or pending else "succeeded", stats,
                            f"pending={pending}; failed={failures}; see site_sync_report.json" if failures or pending else None)
        LOG.info("SITE SYNC %s", {k:v for k,v in report.items() if k!='gaps'})
        return report
    except BaseException as exc:
        frontier.report(phase="interrupted_or_failed", error_type=type(exc).__name__)
        db.finish_crawl_run(run_id, "failed", stats, type(exc).__name__)
        raise
    finally:
        frontier.db.close()
        lock_file.seek(0); msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1); lock_file.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--max-fetch", type=int, default=0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    run_site_sync(resume=args.resume, discover_only=args.discover_only, max_fetch=args.max_fetch)
