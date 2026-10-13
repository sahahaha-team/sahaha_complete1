import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from chatbot.candidate_search import fuse_candidates, complete_direct_candidates
from chatbot.retriever import HybridRetriever
from chatbot.evidence_decision import document_decision


def document(name, body, *, url=None, **extras):
    return {'id':name,'content':body,'metadata':{'title':name,
        'url':url or 'https://www.saha.go.kr/portal/'+name,'source_type':'crawled_page'}, **extras}


class CandidateSearchTests(unittest.TestCase):
    def test_multiple_chunks_cannot_outvote_other_sources(self):
        a=document('a','x',url='a');b=document('b','x',url='b')
        rows=fuse_candidates({'bm25':[a,a,a,b],'vector':[b,a]})
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['retrieval_ranks'],{'bm25':1,'vector':2})
        self.assertEqual(rows[1]['retrieval_ranks'],{'bm25':2,'vector':1})
        self.assertAlmostEqual(rows[0]['rrf_score'],rows[1]['rrf_score'])

    def test_raw_vector_similarity_is_not_replaced_by_rank_score(self):
        doc=document('a','x',similarity=.53)
        result=fuse_candidates({'vector':[doc]})[0]
        self.assertEqual(result['vector_similarity'],.53)
        self.assertLess(result['rrf_score'],.1)

    def test_original_is_kept_when_vector_chunk_shares_url(self):
        raw=document('여권','## 여권\n긴 원문 전체',url='same')
        chunk={'id':'chunk','content':'사진 2매','metadata':{'url':'same'},'similarity':.7}
        result=fuse_candidates({'original':[raw],'vector':[chunk]})[0]
        self.assertEqual(result['content'],raw['content'])
        self.assertEqual(result['_match_content'],'사진 2매')

    def test_keyword_hits_without_requested_facts_trigger_vector_search(self):
        retriever=object.__new__(HybridRetriever)
        doc=document('대형폐기물','## 대형폐기물\n수수료 안내',bm25_score=100)
        retriever.bm25=SimpleNamespace(enabled=True,search=lambda *a,**kw:[doc])
        retriever.vs=Mock()
        retriever.vs.hybrid_search.return_value=[]
        retriever.vs.similarity_search.return_value=[]
        result=retriever.search('대형폐기물 수수료 얼마인가요?')
        self.assertTrue(result['retrieval']['vector_invoked'])
        retriever.vs.hybrid_search.assert_called_once()

    def test_conflicting_complete_sources_do_not_skip_semantics(self):
        a=document('여권','## 여권\n수수료: 50,000원',url='one')
        b=document('여권','## 여권\n수수료: 60,000원',url='two')
        self.assertEqual(complete_direct_candidates('여권 수수료',[a,b],{'여권'}),[])

    def test_vector_failure_retains_lexical_candidates_with_failure_reason(self):
        retriever=object.__new__(HybridRetriever)
        doc=document('대형폐기물','대형폐기물 일반 안내')
        retriever.bm25=SimpleNamespace(enabled=True,search=lambda *a,**kw:[doc])
        retriever.vs=SimpleNamespace(hybrid_search=Mock(side_effect=RuntimeError('offline')))
        result=retriever.search('대형폐기물 신청 방법')
        self.assertTrue(result['degraded'])
        self.assertEqual(result['results'][0]['content'],doc['content'])
        self.assertEqual(result['reason'],'vector_search_failed')

    def test_institution_hours_are_not_pregnancy_program_hours(self):
        doc=document('임신 초기검사 지원','## 임신 초기검사 지원\n사하구 보건소\n이용시간: 09:00~11:30')
        self.assertFalse(document_decision('사하구 보건소 몇 시부터 진료해요?',doc,{'보건소'})['relevant'])

    def test_other_district_cannot_borrow_saha_hours(self):
        doc=document('보건소','## 사하구 보건소\n진료시간: 09:00~18:00')
        self.assertFalse(document_decision('부산진구 보건소 진료시간',doc,{'보건소'})['relevant'])


if __name__ == '__main__':unittest.main()
