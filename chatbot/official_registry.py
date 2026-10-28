"""Exact, reviewed partner pages. A government-looking domain is not enough."""
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse


@lru_cache(maxsize=1)
def reviewed_external_urls() -> frozenset[str]:
    path = Path(__file__).resolve().parents[1] / 'resources/additional_official_pages.json'
    records = json.loads(path.read_text(encoding='utf-8'))
    authorities = {'www.busan.go.kr': '부산광역시'}
    return frozenset(row['url'] for row in records if row.get('external_official') is True
                     and (parsed := urlparse(row.get('url', ''))).scheme == 'https'
                     and row.get('authority') == authorities.get(parsed.hostname)
                     and parsed.hostname in authorities and not parsed.username
                     and not parsed.password and parsed.port in (None, 443) and not parsed.fragment)


def reviewed_external_url(url: str) -> bool:
    return url in reviewed_external_urls()
