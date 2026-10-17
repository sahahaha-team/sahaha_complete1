"""Local pair relevance for ambiguous candidates, not a factual answer judge.

Model weights must already exist locally. Scores remain raw logits. A source
binding is invalidated by either a changed query or a changed original body.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from collections import OrderedDict

from config import (RAG_RERANK_ENABLED, RAG_RERANK_MODEL, RAG_RERANK_CACHE_DIR,
                    RAG_RERANK_LIMIT, RAG_SEMANTIC_MIN_LOGIT, RAG_SEMANTIC_MIN_MARGIN)

logger=logging.getLogger(__name__)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def source_hash(document: dict) -> str:
    from chatbot.evidence_decision import source_body
    meta = document.get('metadata') or {}
    return text_hash(str(meta.get('url') or '') + '\n' + str(meta.get('title') or '') + '\n' + source_body(document))


def eligible_candidates(query: str, documents: list[dict], keywords: set[str]) -> list[dict]:
    from chatbot.evidence import is_official_document, is_answerable_document, is_time_compatible, is_service_source
    from chatbot.evidence_decision import source_body
    from chatbot.query_subject import SERVICE_NAMES, compact, service_term_present
    known = keywords.intersection(SERVICE_NAMES)
    return [doc for doc in documents if is_official_document(doc) and is_answerable_document(query, doc)
        and is_time_compatible(query, doc) and is_service_source(query, doc, keywords)
        and all(service_term_present(term, str((doc.get('metadata') or {}).get('title') or '') + '\n' + source_body(doc)) for term in known)]


def semantic_keywords(query: str, document: dict, default: set[str]) -> set[str]:
    record=document.get('_semantic_support') or {}
    from chatbot.evidence_decision import source_body
    if (record.get('model') != RAG_RERANK_MODEL or record.get('query_hash') != text_hash(query)
            or record.get('source_hash') != source_hash(document)
            or float(record.get('logit',-100)) < RAG_SEMANTIC_MIN_LOGIT
            or (float(record.get('margin',-100)) < RAG_SEMANTIC_MIN_MARGIN and not record.get('single_known_subject'))):
        return default
    terms=set(record.get('terms') or [])
    from chatbot.query_subject import SERVICE_NAMES, service_term_present
    known = default.intersection(SERVICE_NAMES)
    if known and (not known.issubset(terms) or not all(service_term_present(term,
            str((document.get('metadata') or {}).get('title') or '') + '\n' + source_body(document)) for term in known)):
        return default
    return terms or default


def has_semantic_support(query: str, document: dict) -> bool:
    return bool(semantic_keywords(query,document,set()))


def passages(query: str, document: dict, keywords: set[str]) -> list[str]:
    from chatbot.evidence_decision import source_body
    from chatbot.query_subject import compact
    body=source_body(document)
    title=str((document.get('metadata') or {}).get('title') or '')
    windows=[body[i:i+700] for i in range(0,len(body),500)] or ['']
    # Score current source windows; an outdated embedded chunk cannot itself
    # become evidence after its owning original was changed or deleted.
    wanted=compact(str(document.get('_match_content') or ''))[:100]
    ranked=sorted(enumerate(windows),key=lambda pair:(
        int(bool(wanted) and wanted in compact(pair[1])),
        sum(word in compact(pair[1]) for word in keywords)),reverse=True)
    chosen=sorted(ranked[:2],key=lambda pair:pair[0])
    return [title+'\n'+text for _,text in chosen if text.strip()]


class SemanticRanker:
    def __init__(self):
        self._lock=threading.RLock();self._model=None;self._tokenizer=None
        self._failed_at=0.0;self._cache=OrderedDict();self._warmed=False

    def warmup(self):
        """Prepare one bounded CPU batch before accepting the first request.

        Synthetic scores are discarded; no source or selection cache is filled.
        Shape-dependent costs can still occur for other batch sizes.
        """
        with self._lock:
            if not self._load(): return False
            if self._warmed: return True
            try:
                import torch
                batch_size=min(4,max(1,RAG_RERANK_LIMIT))
                encoded=self._tokenizer(['공식 행정 안내']*batch_size,
                    ['신청 대상과 절차를 공식 자료에서 확인합니다.']*batch_size,
                    padding='max_length',truncation=True,max_length=384,return_tensors='pt')
                with torch.inference_mode(): self._model(**encoded)
                self._warmed=True
                logger.info('로컬 의미 재정렬 첫 계산 준비 완료')
                return True
            except Exception as exc:
                logger.warning('의미 재정렬 첫 계산 준비 실패 (%s)',type(exc).__name__)
                return False

    def _load(self):
        if self._model is not None:return True
        if not RAG_RERANK_ENABLED or time.monotonic()-self._failed_at<60:return False
        try:
            from transformers import AutoTokenizer,AutoModelForSequenceClassification
            self._tokenizer=AutoTokenizer.from_pretrained(RAG_RERANK_MODEL,
                cache_dir=RAG_RERANK_CACHE_DIR,local_files_only=True,trust_remote_code=False)
            self._model=AutoModelForSequenceClassification.from_pretrained(RAG_RERANK_MODEL,
                cache_dir=RAG_RERANK_CACHE_DIR,local_files_only=True,trust_remote_code=False,use_safetensors=True).eval()
            logger.info('로컬 의미 재정렬 준비 완료')
            return True
        except Exception as exc:
            self._model=None;self._failed_at=time.monotonic()
            logger.warning('의미 재정렬 준비 실패 (%s); 기존 공식 근거 검사를 유지합니다',type(exc).__name__)
            return False

    def rerank(self, query: str, documents: list[dict], keywords: set[str]) -> tuple[list[dict],dict]:
        from chatbot.evidence import is_official_document,is_answerable_document,is_time_compatible
        from chatbot.evidence_decision import source_body
        from chatbot.query_subject import fallback_keywords
        started=time.perf_counter()
        eligible = eligible_candidates(query, documents, keywords)
        selected=eligible[:max(1,RAG_RERANK_LIMIT)]
        with self._lock:
            if not selected or not self._load():return documents,{'used':False,'reason':'model_unavailable' if selected else 'no_candidates'}
            import torch
            pairs=[];bindings=[];scored=[]
            for doc in selected:
                key=(RAG_RERANK_MODEL,query,source_hash(doc))
                cached=self._cache.get(key)
                if cached and time.monotonic()-cached[0]<900:
                    scored.append((doc,cached[1]));self._cache.move_to_end(key)
                else:
                    for passage in passages(query,doc,keywords):
                        bindings.append((doc,key));pairs.append((query,passage))
            if pairs:
                try:
                    values=[]
                    for i in range(0,len(pairs),4):
                        batch=pairs[i:i+4]
                        encoded=self._tokenizer([q for q,_ in batch],[p for _,p in batch],
                            padding=True,truncation=True,max_length=384,return_tensors='pt')
                        with torch.inference_mode():values.extend(self._model(**encoded).logits.squeeze(-1).tolist())
                    by_key={}
                    for (doc,key),value in zip(bindings,values):
                        by_key[key]=(doc,max(float(value),by_key.get(key,(None,-100))[1]))
                    for key,(doc,value) in by_key.items():
                        self._cache[key]=(time.monotonic(),value);scored.append((doc,value))
                    while len(self._cache)>256:self._cache.popitem(last=False)
                except Exception as exc:
                    logger.warning('의미 재정렬 실패 (%s)',type(exc).__name__)
                    return documents,{'used':False,'reason':'rerank_failed'}
            scored.sort(key=lambda row:row[1],reverse=True)
            if not scored:return documents,{'used':False,'reason':'empty_source'}
            top=scored[0][1];second=scored[1][1] if len(scored)>1 else top
            margin=top-second
            from chatbot.query_subject import SERVICE_NAMES
            single_known = len(scored) == 1 and bool(keywords.intersection(SERVICE_NAMES))
            ranked=[]
            for index,(doc,logit) in enumerate(scored):
                item={**doc,'rerank_logit':round(logit,5)}
                if index==0 and logit>=RAG_SEMANTIC_MIN_LOGIT and (margin>=RAG_SEMANTIC_MIN_MARGIN or single_known):
                    title=str((doc.get('metadata') or {}).get('title') or '')
                    terms=fallback_keywords(title)
                    from chatbot.query_subject import SERVICE_NAMES, compact
                    known = keywords.intersection(SERVICE_NAMES)
                    # A named topic stays required even if the model ranks a
                    # different service highly. Meaning support may bridge
                    # wording, never replace 자전거 with 버스 or another entity.
                    terms = known or terms
                    if terms:
                        item['_semantic_support']={'model':RAG_RERANK_MODEL,'query_hash':text_hash(query),
                            'source_hash':source_hash(doc),'logit':logit,'margin':margin,'terms':sorted(terms),
                            'single_known_subject':single_known}
                ranked.append(item)
            seen={(doc.get('metadata') or {}).get('url') for doc in ranked}
            ranked += [doc for doc in eligible if (doc.get('metadata') or {}).get('url') not in seen]
            info={'used':True,'model':RAG_RERANK_MODEL,'scored_sources':len(scored),
                  'seconds':round(time.perf_counter()-started,4),'top_logit':round(top,4),'margin':round(margin,4)}
            logger.info('의미 재정렬: 출처=%s, 소요=%.3fs',len(scored),info['seconds'])
            return ranked,info


semantic_ranker=SemanticRanker()
