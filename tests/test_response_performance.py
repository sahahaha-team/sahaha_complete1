import json
import threading
import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from chatbot.bm25_index import BM25Index
from chatbot.crawled_pages import CrawledPageIndex
from chatbot.retriever import HybridRetriever
from chatbot.source_pages import hydrate_source_documents, source_document
from chatbot.model_plan_cache import ModelPlanCache, model_plan_cache
from chatbot.grounded_planner import answer_with_grounded_model, prepare_evidence, render_plan
from chatbot.query_subject import query_keywords
from chatbot.answer_goal import answer_goal
from chatbot.evidence import topic_support


URL = 'https://www.saha.go.kr/portal/contents.do?mId=0405140000'


def document(body='정화조 청소는 연 1회 실시해야 합니다.'):
    return {'content': body, 'metadata': {'url': URL, 'title': '정화조 청소', 'source_type': 'crawled_page'}}


class RefreshTests(unittest.TestCase):
    def index(self):
        index = object.__new__(BM25Index)
        index._refresh_lock = threading.RLock()
        index._build_lock = threading.Lock()
        index._tokenize_lock = threading.Lock()
        index._refreshing = False
        index._last_attempt = 0
        index._last_built = time.monotonic() - 301
        index.kiwi = SimpleNamespace(tokenize=lambda text: [SimpleNamespace(form=w, tag='NNG') for w in text.split()])
        index.bm25 = SimpleNamespace(get_scores=lambda _: [2.0])
        index.doc_ids = ['old']
        index.doc_contents = ['정화조']
        index.doc_metadata = [{}]
        index.enabled = True
        return index

    def test_expired_index_serves_consistent_results_while_one_refresh_builds(self):
        index = self.index()
        started, release = threading.Event(), threading.Event()
        def execute():
            started.set()
            release.wait(3)
            return SimpleNamespace(data=[{'id': 'new', 'content': '정화조', 'metadata': {}},
                                        {'id': 'two', 'content': '여권', 'metadata': {}},
                                        {'id': 'three', 'content': '보건소', 'metadata': {}}])
        client = Mock()
        client.table.return_value.select.return_value.range.return_value.execute.side_effect = execute
        with patch('chatbot.bm25_index.get_supabase', return_value=client):
            try:
                self.assertEqual(index.search('정화조')[0]['id'], 'old')
                self.assertTrue(started.wait(1))
                done = threading.Event()
                rows = []
                def search():
                    rows.extend(index.search('정화조'))
                    done.set()
                query_thread = threading.Thread(target=search)
                query_thread.start()
                self.assertTrue(done.wait(1), 'consultation waited for the corpus rebuild')
                self.assertEqual(rows[0]['id'], 'old')
                self.assertEqual(client.table.call_count, 1)
            finally:
                release.set()
                query_thread.join(3) if 'query_thread' in locals() else None
                with index._build_lock:
                    pass
            self.assertEqual(index.search('정화조')[0]['id'], 'new')

    def test_failed_or_empty_rebuild_does_not_mix_old_rows_with_new_scorer(self):
        index = self.index()
        client = Mock()
        execute = client.table.return_value.select.return_value.range.return_value.execute
        execute.side_effect = RuntimeError('database unavailable')
        with patch('chatbot.bm25_index.get_supabase', return_value=client):
            index.rebuild()
            self.assertEqual(index._search_locked('정화조', 1)[0]['id'], 'old')
            execute.side_effect = None
            execute.return_value = SimpleNamespace(data=[])
            index.rebuild()
            self.assertEqual(index._search_locked('정화조', 1), [])

    def test_page_refresh_retains_snapshot_without_blocking_queries(self):
        index = CrawledPageIndex(Mock())
        index._pages = [{'url': 'old'}]
        index._loaded_at = time.monotonic() - 301
        started, release = threading.Event(), threading.Event()
        def execute():
            started.set()
            release.wait(3)
            return SimpleNamespace(data=[{'url': 'new'}])
        index.client.table.return_value.select.return_value.order.return_value.range.return_value.execute.side_effect = execute
        try:
            self.assertEqual(index._snapshot(), [{'url': 'old'}])
            self.assertTrue(started.wait(1))
            self.assertEqual(index._snapshot(), [{'url': 'old'}])
            self.assertEqual(index.client.table.call_count, 1)
        finally:
            release.set()
        deadline = time.monotonic() + 2
        while index._refreshing and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertEqual(index._snapshot(), [{'url': 'new'}])


class SourceReuseTests(unittest.TestCase):
    def test_known_official_url_skips_global_search_when_complete_original_exists(self):
        retriever = object.__new__(HybridRetriever)
        retriever.search_crawled_pages = Mock(return_value=[document()])
        retriever.db = Mock()
        retriever.bm25 = Mock()
        result = retriever.search_official_url('정화조 청소 주기', URL)
        self.assertEqual(result['results'], [document()])
        retriever.bm25.search.assert_not_called()
        retriever.db.client.table.assert_not_called()

    def test_freshness_fetch_replaces_a_stale_candidate_body_and_supplies_full_original(self):
        retriever = object.__new__(HybridRetriever)
        retriever.db = Mock()
        client = retriever.db.client
        client.table.return_value.select.return_value.in_.return_value.execute.return_value = SimpleNamespace(data=[{
            'url': URL, 'content': '정화조 청소는 변경된 기준을 확인해야 합니다.', 'attachments': [],
            'last_checked_at': datetime.now(timezone.utc).isoformat()}])
        old = document()
        fresh = retriever.filter_fresh_results('정화조 청소 주기', [old])
        self.assertNotIn('연 1회', fresh[0]['content'])
        self.assertIn('연 1회', old['content'])
        hydrated = hydrate_source_documents(fresh, client)
        self.assertEqual(source_document(hydrated[0], client)[0], fresh[0]['content'])
        self.assertEqual(client.table.call_count, 1)
        client.table.return_value.select.return_value.in_.return_value.execute.return_value.data[0]['last_checked_at'] = '1970-01-01T00:00:00+00:00'
        self.assertEqual(retriever.filter_fresh_results('정화조 청소 주기', [old]), [])

    def test_batch_originals_are_reused_after_model_failure_and_missing_rows_fail_closed(self):
        docs = [document(), document()]
        for doc in docs:
            doc['metadata']['source_type'] = 'official_page'
        client = Mock()
        client.table.return_value.select.return_value.in_.return_value.execute.return_value = SimpleNamespace(data=[{
            'url': URL, 'content': '정화조 청소는 연 1회 실시해야 합니다.', 'attachments': []}])
        hydrated = hydrate_source_documents(docs, client)
        self.assertIn('연 1회', source_document(hydrated[0], client)[0])
        self.assertIn('연 1회', source_document(hydrated[1], client)[0])
        self.assertEqual(client.table.call_count, 1)
        self.assertNotIn('_raw_page', docs[0])
        client.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []
        missing = hydrate_source_documents(docs, client)
        self.assertEqual(source_document(missing[0], client)[0], '')
        self.assertEqual(client.table.call_count, 2)


class ModelSelectionTests(unittest.TestCase):
    def test_repeated_selection_is_revalidated_and_hidden_source_changes_invalidate_cache(self):
        model = Mock()
        model.model = 'performance-test-model'
        model.model_copy.return_value.invoke.return_value = SimpleNamespace(
            content=json.dumps({'mode': 'answer', 'source': 0, 'units': [0]}), response_metadata={})
        docs = [document()]
        query = '정화조 청소 주기 캐시검증'
        self.assertIsNotNone(answer_with_grounded_model(query, docs, None, {'정화조', '청소'}, model))
        self.assertIsNotNone(answer_with_grounded_model(query, docs, None, {'정화조', '청소'}, model))
        self.assertEqual(model.model_copy.return_value.invoke.call_count, 1)
        docs[0]['content'] += '\n※ 별도 기준이 있는 시설은 예외입니다.'
        result = answer_with_grounded_model(query, docs, None, {'정화조', '청소'}, model)
        self.assertIn('예외', result['answer'])
        self.assertEqual(model.model_copy.return_value.invoke.call_count, 2)

    def test_cache_expires_and_has_a_size_limit(self):
        cache = ModelPlanCache(maxsize=1, ttl=30)
        plan = {'mode': 'answer', 'source': 0, 'units': [0]}
        with patch('chatbot.model_plan_cache.time.monotonic', return_value=10):
            cache.put('a', plan)
            cache.put('b', plan)
            self.assertIsNone(cache.get('a'))
            self.assertEqual(cache.get('b'), plan)
        with patch('chatbot.model_plan_cache.time.monotonic', return_value=40):
            self.assertIsNone(cache.get('b'))

    def test_electronic_services_use_complete_online_instructions_and_exclude_offline_counters(self):
        query = '사하구 홈페이지에서 이용할 수 있는 전자민원 서비스에는 무엇이 있나요?'
        self.assertEqual(answer_goal(query), 'services')
        self.assertEqual(query_keywords(query, ['홈페이지', '전자', '민원', '서비스']), {'전자민원'})
        body = ('온라인으로 민원 상담 및 접수를 하시려면\n국민신문고\n를 이용해주시면 됩니다.\n'
                '그 외 각종 주민등록등본 등의 서류 발급은 왼쪽 메뉴 첫 번째\n정부24\n로 온라인 발급하실수 있습니다.\n'
                '업무내용 : 각종 인허가 접수 및 허가증 교부, 진정서 접수')
        doc = document(body)
        doc['metadata']['title'] = '민원실 이용안내'
        packets = prepare_evidence(query, [doc], None, {'전자민원'})
        self.assertEqual(len(packets), 1)
        self.assertEqual(len(packets[0]['units']), 3)
        from chatbot.grounded_planner import eligible_ids
        packets[0]['eligible_ids'] = eligible_ids(query, packets[0], {'전자민원'})
        self.assertEqual(packets[0]['eligible_ids'], {0, 1})
        result = render_plan(query, {'mode': 'answer', 'source': 0, 'units': [0, 1]}, packets, {'전자민원'})
        self.assertIn('국민신문고', result['answer'])
        self.assertIn('정부24', result['answer'])
        self.assertIsNone(render_plan(query, {'mode': 'answer', 'source': 0, 'units': [2]}, packets, {'전자민원'}))
        self.assertFalse(topic_support(document('온라인 이벤트 참여 안내'), {'전자민원'})[0])

    def test_online_guide_can_establish_service_kind_without_repeating_online_in_each_sentence(self):
        doc = document("전자민원창구\n민원상담은 국민신문고로 통합하여 운영하고 있습니다.\n별도 회원가입 또는 로그인이 필요합니다.")
        doc['metadata']['title'] = '전자민원창구'
        query = '어떤 전자민원 서비스를 이용할 수 있나요?'
        packets = prepare_evidence(query, [doc], None, {'전자민원'})
        from chatbot.grounded_planner import eligible_ids
        self.assertEqual(eligible_ids(query, packets[0], {'전자민원'}), {1})


if __name__ == '__main__':
    unittest.main()
