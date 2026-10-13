"""Read dated report provenance and labelled table cells without inventing statistics."""
from __future__ import annotations

import re

from chatbot.query_subject import compact
from chatbot.evidence import is_time_compatible


def is_report_query(query: str) -> bool:
    return bool(re.search(r'보고서|분석보고|분석기간|방문.*통계',query))


def report_answer(query: str, documents: list[dict]) -> dict | None:
    from chatbot.bm25_index import _init_kiwi
    ignored = {'보고서','분석','결과','기간','자료','데이터','통계','건수','년','구청','사하구','사하구청','분석보고서'}
    terms = {compact(t.form) for t in _init_kiwi().tokenize(query)
             if t.tag.startswith('NN') and len(t.form) >= 2 and t.form not in ignored}
    ranked = []
    for doc in documents:
        meta = doc.get('metadata') or {}
        if meta.get('source_type') != 'official_report' or not is_time_compatible(query, doc):
            continue
        title = compact(str(meta.get('source_title') or meta.get('title') or ''))
        score = sum(t in title for t in terms)
        if score:
            ranked.append((score,doc))
    if not ranked:
        return None
    best = max(score for score,_ in ranked)
    docs = [d for score,d in ranked if score == best]
    periods = bool(re.search(r'기간|몇\s*년.*(?:자료|분석)|언제.*자료',query))
    if periods:
        doc = min(docs,key=lambda d:int((d.get('metadata') or {}).get('page_number') or 999))
        meta = doc['metadata']
        period = meta.get('data_period')
        if not period:
            return None
        answer = '**보고서의 자료 기준 기간**\n- ' + period
        analysis = re.search(r'분석기간\s*[:：]\s*([^\n]+)',doc.get('content') or '')
        if analysis:
            answer += '\n- 분석 작업 기간: ' + analysis[1].strip()
        if meta.get('issued_at'):
            answer += '\n- 보고서 작성일: ' + meta['issued_at']
        answer += '\n\n현재 행정서비스의 운영 조건을 나타내는 자료는 아닙니다.'
        return {'answer':answer,'documents':[doc],'is_clarification':False,'answer_method':'report_provenance'}
    years = re.findall(r'(20\d{2})\s*년',query)
    if not years or not re.search(r'몇\s*건|건수|몇\s*명|방문자\s*수',query):
        return None
    field_query = re.split(r'보고서(?:에서|의)?',query)[-1]
    labels = {compact(t.form) for t in _init_kiwi().tokenize(field_query)
              if t.tag.startswith('NN') and len(t.form) >= 2}
    candidates = []
    for doc in docs:
        for line in (doc.get('content') or '').splitlines():
            match = re.fullmatch(r'(20\d{2}년) — ([^:：]+): ([\d,]+)',line.strip())
            if not match or match[1][:4] not in years:
                continue
            field = compact(match[2])
            score = sum(term in field or field in term for term in labels if term not in ignored)
            if score:
                candidates.append((score,line.strip(),doc))
    if not candidates:
        return None
    score = max(x[0] for x in candidates)
    chosen = [x for x in candidates if x[0] == score]
    # Conflicting values for one requested column are an extraction problem.
    values = {x[1] for x in chosen}
    if len(values) != 1:
        return None
    doc = chosen[0][2]
    meta = doc['metadata']
    return {'answer':'**공식 분석 보고서의 과거 통계**\n- '+chosen[0][1]+'\n- 자료 기준 기간: '+str(meta.get('data_period') or '미상'),
            'documents':[doc],'is_clarification':False,'answer_method':'report_table'}


def answer_official_report(query: str, client) -> dict | None:
    if not is_report_query(query):
        return None
    try:
        rows = client.table('documents').select('content,metadata').eq(
            'metadata->>source_type','official_report').limit(500).execute().data or []
        urls = {r['metadata']['url'] for r in rows}
        originals = client.table('raw_pages').select('url,content').in_('url',list(urls)).execute().data if urls else []
        bodies = {r['url']:r['content'] for r in originals or []}
        docs = [{**r,'content':bodies.get(r['metadata']['url']) or r['content']} for r in rows]
        return report_answer(query,docs)
    except Exception:
        return None
