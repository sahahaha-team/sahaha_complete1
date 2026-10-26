"""Read current originals, retaining compatibility before the HTML migration."""
import logging
import time

logger = logging.getLogger(__name__)


def read_raw_pages(client, fields: str, *, url=None, urls=None, limit=None, offset=None, count=None, order=None):
    def read(selected):
        query = client.table('raw_pages').select(selected)
        if url is not None:
            query = query.eq('url',url)
        if urls is not None:
            query = query.in_('url',list(urls))
        if limit is not None:
            query = query.limit(limit)
        if order is not None:
            query = query.order(order)
        if offset is not None and count is not None:
            query = query.range(offset, offset + count - 1)
        for attempt in range(2):
            try:
                return query.execute().data or []
            except Exception as exc:
                code=str(getattr(exc,'code',''))
                if attempt or code not in {'500','502','503','504','520','521','522','523','524'}:
                    raise
                # Read-only GET, once. Never reuse stale facts, retry writes,
                # or treat authorization/schema errors as temporary outages.
                logger.warning('공식 원문 일시 조회 오류: status=%s; 1회 재확인',code)
                time.sleep(.15)
    try:
        return read(fields)
    except Exception as exc:
        message = str(exc).lower()
        code = str(getattr(exc,'code',''))
        if ('raw_html' not in fields.split(',') or 'raw_html' not in message
                or not (code in ('42703','PGRST204') or 'does not exist' in message
                        or 'schema cache' in message or 'could not find' in message)):
            raise
        logger.warning('HTML 열 미적용: 기존 공식 텍스트 원문으로 조회합니다.')
        return read(','.join(field for field in fields.split(',') if field != 'raw_html'))
