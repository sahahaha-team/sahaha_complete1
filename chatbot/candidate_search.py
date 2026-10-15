"""Adaptive retrieval: verified originals first, otherwise fused candidates.

RRF operates on source ranks, with at most one vote per URL per retriever.
It does not establish answerability. The current original is checked afterwards.
"""
from __future__ import annotations

import logging
import re
import time

from chatbot.evidence_decision import document_decision
from chatbot.query_subject import normalize_query, compact, SERVICE_NAMES
from chatbot.crawled_pages import page_rank
from config import RAG_CANDIDATE_LIMIT, RAG_RRF_K, VECTOR_CANDIDATE_MIN_SIMILARITY

logger = logging.getLogger(__name__)


def source_key(document: dict) -> str:
    return str((document.get('metadata') or {}).get('url') or document.get('id') or document.get('content') or '')


def fuse_candidates(rankings: dict[str, list[dict]], *, limit: int = 30, rank_constant: int = 60) -> list[dict]:
    candidates = {}
    for name, documents in rankings.items():
        seen = set()
        for document in documents:
            key = source_key(document)
            if not key or key in seen: continue
            seen.add(key)
            rank = len(seen)
            current = candidates.get(key)
            if current is None:
                current = {**document, 'retrieval_ranks': {}, 'rrf_score': 0.0,
                           'vector_similarity': 0.0, 'bm25_score': 0.0, '_match_content': document.get('content') or ''}
                candidates[key] = current
            elif (document.get('metadata') or {}).get('source_type') == 'crawled_page':
                # Keep the full original, never replace it with a short chunk.
                current.update(content=document.get('content') or '', metadata=document.get('metadata') or {})
                if '_raw_page' in document: current['_raw_page'] = document['_raw_page']
            current['retrieval_ranks'][name] = rank
            current['rrf_score'] += 1 / (max(1,rank_constant) + rank)
            if name == 'vector':
                value=float(document.get('vector_similarity',document.get('similarity',0)) or 0)
                current['vector_similarity'] = max(current['vector_similarity'], value)
                current['_match_content'] = document.get('content') or current['_match_content']
            current['bm25_score'] = max(current['bm25_score'],float(document.get('bm25_score') or 0))
    return sorted(candidates.values(),key=lambda doc:doc['rrf_score'],reverse=True)[:limit]


def complete_direct_candidates(query: str, documents: list[dict], keywords: set[str]) -> list[dict]:
    complete=[]
    names=keywords.intersection(SERVICE_NAMES) - {'보건소','구청','자전거','냉장고','세탁기','쓰레기','디지털','컴퓨터'}
    for doc in documents:
        meta=doc.get('metadata') or {}
        if meta.get('source_type') != 'crawled_page' and '_raw_page' not in doc: continue
        heading=compact(str(meta.get('title') or '') + ' ' + next((u.lstrip('# ') for u in
            str(doc.get('content') or '').splitlines() if u.startswith('## ')),''))
        from chatbot.structured_answers import scoped_units
        # A real program subheading inside a generic page can establish the
        # service too. The same scoped field/source checks below still apply.
        heading += compact(' '.join(unit for unit in scoped_units(query, doc.get('content') or '', keywords)
                                   if unit.startswith('#')))
        # A vague entity word or matching noun somewhere in a page cannot
        # bypass meaning search. The requested service must own the heading.
        owners=names or {word for word in keywords if len(word)>=3 and word not in {'보건소','구청','자전거','쓰레기'}}
        if not owners:
            from chatbot.answer_goal import requested_goals
            institution = keywords and keywords.issubset({'보건소','구청'})
            direction = re.search(r'찾아오|오시는길|민원실이용|청사안내', heading)
            if not institution or not direction or not set(requested_goals(query)).issubset({'hours','location'}):
                continue
        elif not all(name in heading for name in owners): continue
        from chatbot.source_scope import focus_terms
        from chatbot.evidence_decision import source_body
        details = focus_terms(query)
        if details and not any(term in compact(source_body(doc)) for term in details):
            continue  # A broad field label cannot resolve an unseen requested detail.
        result=document_decision(query,doc,keywords)
        if result['decision'] == 'supported': complete.append(doc)
    unique={source_key(doc):doc for doc in complete}
    # Different complete sources may disagree on scope or conditions. Inspect
    # semantic candidates instead of assuming the first is the correct source.
    return list(unique.values()) if len(unique)==1 else []


def search_candidates(retriever, query: str, *, k: int = 15) -> dict:
    query=normalize_query(query)
    keywords=retriever._content_keywords(query)
    from chatbot.dept_directory import is_staff_lookup
    if is_staff_lookup(query):
        staff=retriever._staff_results_to_documents(query,limit=k)
        return {'results':staff,'degraded':not bool(staff),'reason':None if staff else 'staff_not_found',
                'retrieval':{'mode':'staff','vector_invoked':False}}
    started=time.perf_counter()
    pages=retriever.search_crawled_pages(query,k=max(k,15))
    from chatbot.faq_targets import match_official_page
    target=match_official_page(query)
    preferred=retriever.search_crawled_pages(query,k=k,url=target) if target else []
    pages=list({source_key(doc):doc for doc in preferred+pages}.values())
    lexical=[]; failures=[]
    try:
        if retriever.bm25 and retriever.bm25.enabled:
            lexical=retriever.bm25.search(query,top_n=max(k,RAG_CANDIDATE_LIMIT))
    except Exception as exc:
        logger.warning('키워드 검색 실패 (%s)',type(exc).__name__);failures.append('bm25_failed')
    direct=complete_direct_candidates(query,pages,keywords)
    if not direct and lexical and getattr(retriever,'db',None) is not None:
        direct=complete_direct_candidates(query,retriever.filter_fresh_results(query,lexical[:5]),keywords)
    if direct:
        return {'results':direct,'degraded':False,'reason':None,
                'retrieval':{'mode':'verified_original','vector_invoked':False,'raw_count':len(pages),
                             'lexical_count':len(lexical),'seconds':round(time.perf_counter()-started,4)}}
    hints=retriever.detect_category(query)
    vector=[]
    try:
        vector=retriever.vs.hybrid_search(query=query,
            category=hints.get('category') if not hints.get('service_type') else None,
            service_type=hints.get('service_type'), k=max(k,RAG_CANDIDATE_LIMIT),
            min_similarity=VECTOR_CANDIDATE_MIN_SIMILARITY)
        # Metadata tags are hints: older or LLM-generated tags may put a
        # relevant official page in another category. Always add the global
        # semantic candidates rather than trusting a nonempty filtered list.
        global_vector=(retriever.vs.similarity_search(query,k=max(k,RAG_CANDIDATE_LIMIT),
            min_similarity=VECTOR_CANDIDATE_MIN_SIMILARITY) if hints.get('category') or hints.get('service_type') else [])
        by_id={str(doc.get('id') or source_key(doc)):doc for doc in vector + global_vector}
        vector=sorted(by_id.values(), key=lambda doc:float(doc.get('vector_similarity',doc.get('similarity',0)) or 0),reverse=True)
    except Exception as exc:
        logger.warning('의미 검색 실패 (%s)',type(exc).__name__);failures.append('vector_search_failed')
    contact_intent=retriever._has_staff_lookup_intent(query)
    if not contact_intent:
        lexical=[doc for doc in lexical if not retriever._is_staff_document(doc)]
        vector=[doc for doc in vector if not retriever._is_staff_document(doc)]
    fused=fuse_candidates({'original':pages,'bm25':lexical,'vector':vector},limit=max(k,RAG_CANDIDATE_LIMIT),rank_constant=RAG_RRF_K)
    details={'mode':'hybrid_rrf','vector_invoked':True,'raw_count':len(pages),
             'lexical_count':len(lexical),'vector_count':len(vector),'failures':failures,
             'seconds':round(time.perf_counter()-started,4)}
    logger.info('검색 확장: 원문=%s, BM25=%s, 벡터=%s, 소요=%.3fs',len(pages),len(lexical),len(vector),details['seconds'])
    return {'results':fused,'degraded':bool(failures),'reason':failures[0] if failures else None,'retrieval':details}
