"""Reuse complete originals within one consultation, without an answer cache."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def hydrate_source_documents(documents: list[dict], client) -> list[dict]:
    urls = {str((doc.get('metadata') or {}).get('url') or '') for doc in documents
            if (doc.get('metadata') or {}).get('source_type') != 'crawled_page'
            and '_raw_page' not in doc
            and (doc.get('metadata') or {}).get('category') != 'staff_directory'} - {''}
    if not urls:
        return documents
    try:
        rows = client.table('raw_pages').select('url,content,attachments').in_('url', sorted(urls)).execute().data or []
        originals = {row['url']: row for row in rows}
    except Exception:
        logger.warning('상담 원문 일괄 조회 실패')
        originals = {}
    # Copies belong only to this request. Missing rows are explicit empty
    # originals, so neither model failure nor fallback repeats the DB call.
    return [{**doc, '_raw_page': originals.get((doc.get('metadata') or {}).get('url'), {})}
            if (doc.get('metadata') or {}).get('url') in urls else doc for doc in documents]


def source_document(document: dict, client) -> tuple[str, dict]:
    meta = document.get('metadata') or {}
    if meta.get('source_type') == 'crawled_page':
        return document.get('content') or '', document
    if '_raw_page' in document:
        row = document['_raw_page']
    else:
        try:
            rows = client.table('raw_pages').select('content,attachments').eq(
                'url', meta.get('url')).limit(1).execute().data or []
            row = rows[0] if rows else {}
        except Exception:
            row = {}
    if 'attachments' in row:
        document = {**document, 'metadata': {**meta, 'attachments': row.get('attachments') or []}}
    return row.get('content') or '', document
