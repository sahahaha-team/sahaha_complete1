"""Search complete official pages alongside chunks; no evaluation data is used."""
from __future__ import annotations
import hashlib
import math
import re
from urllib.parse import urlsplit

from chatbot.source_text import clean_source_text
from chatbot.query_subject import compact, substantive_keywords, subject_query, WEAK_WORDS, AREA_PATTERN
from chatbot.evidence import is_answerable_document, is_official_document, topic_support, is_listing_document
from chatbot.question_intent import requested_field_score, asks_navigation


def asks_catalog_support(query):
    return bool(re.search(r'지원|혜택', query) and asks_navigation(query))


class OfficialPageIndex:
    def __init__(self, rows, sections_by_url, tokenize):
        from rank_bm25 import BM25Okapi
        self.tokenize = tokenize
        self.rows = []
        self.subject_names = set()
        corpus = []
        canonical_pages = {(urlsplit(r.get('url') or '').path, urlsplit(r.get('url') or '').query)
                           for r in rows if urlsplit(r.get('url') or '').hostname == 'www.saha.go.kr'}
        for row in rows:
            url = row.get('url') or ''
            parsed = urlsplit(url)
            if (parsed.hostname != 'www.saha.go.kr' and parsed.path.startswith(('/portal/', '/health/', '/tour/'))
                    and (parsed.path, parsed.query) in canonical_pages):
                continue  # These are aliases of the same council portal, not separate services.
            digest = hashlib.sha256((row.get('content') or '').encode()).hexdigest()
            sections = [s for s in sections_by_url.get(url, []) if s.get('hash') == digest]
            title = row.get('title') or ''
            # The DOM document title on an old chunk is often more specific
            # than the main menu label stored in raw_pages.
            full_title = next((s['heading'] for s in sections if '|' in s['heading']), title)
            if re.search(r'사이트맵|홈페이지이용안내|메인페이지', compact(full_title)):
                continue
            if re.search(r'/(?:main|children|index)\.do$', urlsplit(url).path):
                continue
            body = clean_source_text(row.get('content') or '')
            substantive = re.sub(r'PDF뷰어|PDF|다운로드|확대보기|\s', '', body)
            if len(substantive) < 20 or ('다운로드' in body and len(substantive) < 60):
                continue
            if len(body) < 40 or body.count('(cid:') > 8:
                continue
            is_image = '[이미지 문자 인식 자료:' in body
            meta = {'url': url, 'title': full_title, 'category': row.get('category') or '',
                    'attachments': row.get('attachments') or [], 'section_heading': full_title,
                    'source_type': 'official_ocr' if is_image else 'verified_page' if 'contents.do' in url else 'official_attachment',
                    'page_document': True, 'page_sections': sections,
                    'content_hash': digest}
            document = {'id': 'page:' + url, 'content': body, 'metadata': meta}
            if not is_official_document(document):
                continue
            document['_topic_text'] = compact(full_title + ' ' + body)
            document['_listing_document'] = is_listing_document(document)
            self.rows.append(document)
            for label in [full_title.split('|')[0]] + [s['heading'].split('|')[0] for s in sections]:
                for name in re.split(r'[/|:：()\[\]]', label):
                    name = compact(name)
                    name = re.sub(r'(?:인가요|있나요|이란|은|는)$', '', name)
                    name = re.sub(r'(?:안내|지원사업|사업|지원|관리|제도|개요|서비스|현황)$', '', name)
                    if 4 <= len(name) <= 18 and not re.search(r'신청|지원대상|선정기준|문의|소득|준비|금액|절차|확인', name):
                        self.subject_names.add(name)
            corpus.append(tokenize(full_title) * 3 + tokenize(body[:10000 if 'contents.do' in url else 3500]))
        self.bm25 = BM25Okapi(corpus) if corpus else None

    def focus_keywords(self, query, keywords):
        value = compact(query)
        base = substantive_keywords(keywords)
        names = [name for name in self.subject_names if name in value
                 and not AREA_PATTERN.search(name)
                 and (sum(word in name for word in base) >= max(1, math.ceil(len(base) * .5))
                      or len(name) >= 4 and len(self.tokenize(name)) >= 2 and sum(word in name for word in base) >= 2)
                 and not re.search(r'어떻게|언제|무엇|지원사업|홈페이지|이용방법', name)]
        if names:
            return {name for name in names if not any(name != other and name in other for other in names)}
        return keywords

    def search(self, query, keywords, top_n=30):
        if not self.bm25:
            return []
        topics = substantive_keywords(keywords)
        if re.search(r'서비스.*(?:무엇|종류)|(?:무엇|종류).*서비스', query) and len(topics) == 1:
            parent = next(iter(topics))
            categories = {}
            for row in self.rows:
                labels = [part.strip() for part in row['metadata']['title'].split('|')]
                for position, label in enumerate(labels[1:], 1):
                    if compact(label) == parent:
                        category = labels[position-1]
                        old = categories.get(category)
                        if old is None or len(labels) < old[0]:
                            categories[category] = (len(labels), row)
                        break
            if len(categories) >= 4:
                return [{**row, 'metadata': {**row['metadata'], 'navigation_catalog': name},
                         'bm25_score': 100.0, 'page_score': 100.0}
                        for name, (_, row) in sorted(categories.items())][:min(top_n, 8)]
        query_tokens = self.tokenize(query)
        tokens = self.tokenize(' '.join(keywords)) * 2 + [t for t in self.tokenize(subject_query(query)) if t not in WEAK_WORDS]
        scores = self.bm25.get_scores(tokens)
        candidates = []
        for index, score in enumerate(scores):
            if score <= 0:
                continue
            row = self.rows[index]
            if not is_answerable_document(query, row) or not topic_support(row, topics)[0]:
                continue
            meta = row['metadata']
            labels = [compact(meta['title'].split('|')[0])] + [compact(s['heading']) for s in meta.get('page_sections') or []]
            title_hits = sum(len(w) for w in topics if any(w in label for label in labels))
            title_coverage = title_hits / max(1, sum(map(len, topics)))
            own_title = compact(meta['title'].split('|')[0])
            own_title = re.sub(r'(?:안내|지원사업|지원|운영|사업|제도)$', '', own_title)
            exact = 12 if len(topics) == 1 and own_title in topics else 0
            page = urlsplit(meta['url'])
            # Current service pages outrank incidental mentions in budgets,
            # photographs and neighborhood copies of general council policy.
            service_page = 'contents.do' in page.path
            primary = page.path.startswith(('/portal/', '/health/', '/tour/'))
            explicit_site = bool(re.search(r'도서관|문화회관|문화관광|동주민센터|동행정복지', query))
            scope = 12 if primary else 0 if explicit_site else -10
            relevant_sections = [s for s in meta.get('page_sections') or []
                                 if any(word in compact(s['heading']) for word in topics)]
            field = max([requested_field_score(query, label) for label in labels] +
                        [requested_field_score(query, s['text'][:400]) for s in relevant_sections])
            if '보건소' in query:
                scope += 18 if page.path.startswith('/health/') else -12
            if asks_catalog_support(query):
                scope += 15 if '지원사업' in compact(meta['title']) else -10 if '관련사이트' in own_title else 0
            if re.search(r'인터넷|온라인', query):
                scope += 20 if any(re.search(r'인터넷|온라인|위택스|정부24|국민신문고|복지로', s['text'])
                                   for s in relevant_sections) else -15
                if re.search(r'인터넷|온라인', own_title):
                    scope += 35
            if re.search(r'기간.*아니|연중|언제든|언제나', query):
                scope += 30 if re.search(r'365|연중|언제나|법정기간외', compact(row['content'])) else 0
            # Prefer a catalog of benefit names to a table of income thresholds.
            if re.search(r'급여.*(?:무엇|종류)', query):
                field += min(5, sum(bool(re.search(r'급여\s*[:：]', s['heading']))
                                    for s in meta.get('page_sections') or []))
            value = float(score) + 18 * title_coverage + exact + field * 3 + (6 if service_page else -8) + scope
            value += 2 if page.hostname == 'www.saha.go.kr' else 0
            candidates.append({**row, 'metadata': {**meta, 'query_tokens': query_tokens},
                               'bm25_score': value, 'page_score': value})
        ranked, seen = [], set()
        for row in sorted(candidates, key=lambda row: row['page_score'], reverse=True):
            identity = (compact(row['metadata']['title']), row['metadata']['content_hash'])
            if identity not in seen:
                seen.add(identity)
                ranked.append(row)
        return ranked[:top_n]
