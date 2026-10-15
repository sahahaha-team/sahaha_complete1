import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from chatbot.source_pages import source_document
from chatbot.evidence_decision import source_body
from chatbot.semantic_ranker import source_hash
from chatbot.candidate_search import search_candidates, complete_direct_candidates


class AccuracyPerformanceTests(unittest.TestCase):
    def test_changed_html_invalidates_reused_original_and_its_semantic_binding(self):
        from chatbot.official_content import official_html_text
        row = {'raw_html': '<article><h3>이용안내</h3><p>신청권수: 월 2권</p></article>', 'content': ''}
        doc = {'content': 'old chunk', '_raw_page': row,
               'metadata': {'url': 'https://www.saha.go.kr/portal/test', 'title': '이용안내'}}
        with patch('chatbot.official_content.official_html_text', wraps=official_html_text) as parse:
            before = source_hash(doc)
            self.assertIn('2권', source_body(doc))
            self.assertIn('2권', source_document(doc, None)[0])
            self.assertEqual(parse.call_count, 1, 'the same request parsed an unchanged original again')
            row['raw_html'] = row['raw_html'].replace('2권', '3권')
            self.assertIn('3권', source_document(doc, None)[0])
            self.assertNotEqual(source_hash(doc), before)
            self.assertEqual(parse.call_count, 2)

    def test_unfiltered_vector_expansion_does_not_repeat_the_same_global_lookup(self):
        retriever = SimpleNamespace(
            _content_keywords=lambda q: {'법률'}, search_crawled_pages=Mock(return_value=[]),
            bm25=None, db=None, detect_category=lambda q: {},
            _has_staff_lookup_intent=lambda q: False, _is_staff_document=lambda doc: False,
            vs=SimpleNamespace(hybrid_search=Mock(return_value=[]), similarity_search=Mock(return_value=[])))
        result = search_candidates(retriever, '법률상담 받는 방법')
        self.assertTrue(result['retrieval']['vector_invoked'])
        retriever.vs.hybrid_search.assert_called_once()
        retriever.vs.similarity_search.assert_not_called()

    def test_metadata_hints_still_expand_to_the_global_corpus(self):
        retriever = SimpleNamespace(
            _content_keywords=lambda q: {'법률'}, search_crawled_pages=Mock(return_value=[]),
            bm25=None, db=None, detect_category=lambda q: {'service_type': '민원'},
            _has_staff_lookup_intent=lambda q: False, _is_staff_document=lambda doc: False,
            vs=SimpleNamespace(hybrid_search=Mock(return_value=[]), similarity_search=Mock(return_value=[])))
        search_candidates(retriever, '법률상담 받는 방법')
        retriever.vs.similarity_search.assert_called_once()

    def test_complete_method_in_its_own_subheading_can_skip_ambiguous_candidates(self):
        doc = {'content': '## 폐기물\n### 대형폐기물 배출 처리안내\n처리방법 처리업체에 직접 전화 또는 문자 접수\n단, 원형훼손제품은 제외 (유상 처리)',
               'metadata': {'url': 'https://www.saha.go.kr/portal/test', 'title': '폐기물', 'source_type': 'crawled_page'}}
        self.assertEqual(complete_direct_candidates('대형폐기물 배출 방법', [doc], {'대형폐기물'}), [doc])
        missing = {**doc, 'content': '## 폐기물\n### 대형폐기물 배출 처리안내\n수수료 안내'}
        self.assertEqual(complete_direct_candidates('대형폐기물 배출 방법', [missing], {'대형폐기물'}), [])
