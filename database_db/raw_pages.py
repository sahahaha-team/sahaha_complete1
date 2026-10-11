"""Read current originals, retaining compatibility before the HTML migration."""
import logging

logger = logging.getLogger(__name__)


def read_raw_pages(client, fields: str, *, url=None, urls=None, limit=None):
    def read(selected):
        query = client.table('raw_pages').select(selected)
        if url is not None:
            query = query.eq('url',url)
        if urls is not None:
            query = query.in_('url',list(urls))
        if limit is not None:
            query = query.limit(limit)
        return query.execute().data or []
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
