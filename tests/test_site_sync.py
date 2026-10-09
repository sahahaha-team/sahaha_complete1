"""Scope/security and resumability regressions for comprehensive collection."""
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import json
import hashlib
from crawler.site_scope import RobotsRules, canonical_url, skip_reason, site_category
from crawler.site_sync import Frontier
from crawler.saha_crawler import SahaCrawler
from crawler.page_sections import extract_sections


class SiteScopeTests(unittest.TestCase):
    def test_binary_document_text_and_nested_metadata_are_database_safe(self):
        from crawler.site_sync import normalize_resource
        row = {'content': '지원금\x00200만원\ud800', 'title': '공식\x00문서',
               'sections': json.dumps([{'heading': '대상\x00', 'text': '첫째\x00200만원'}]),
               'attachments': json.dumps([{'name': '신청서\x00', 'url': 'https://www.saha.go.kr/a.pdf'}])}
        safe = normalize_resource(row)
        self.assertEqual(safe['content'], '지원금 200만원 ')
        self.assertEqual(json.loads(safe['sections'])[0]['text'], '첫째 200만원')
        self.assertEqual(json.loads(safe['attachments'])[0]['name'], '신청서 ')
        self.assertEqual(normalize_resource(safe), safe)

    def test_failed_checkpoint_is_sanitized_and_successfully_indexed_on_resume(self):
        from crawler.site_sync import index_fetched
        content = '문서\x00제목\n신청 대상 및 지원 조건은 공식 안내문에서 확인합니다. ' * 4
        with tempfile.TemporaryDirectory() as temp:
            frontier = Frontier(Path(temp) / 'state.sqlite3')
            url = 'https://www.saha.go.kr/guide.pdf'
            frontier.add(url)
            frontier.update(url, status='fetched', title='신청\x00안내', content=content,
                            checked_at='2000-01-01T00:00:00+00:00',
                            sections=json.dumps([{'heading': '문서\x00제목', 'text': content}]))
            frontier.report = Mock()
            with patch('database_db.database.Database') as database, patch('database_db.vector_store.VectorStore') as vector_store:
                db = database.return_value
                db.get_all_urls.return_value = set()
                self.assertEqual(index_fetched(frontier), 1)
                raw = db.client.table.return_value.upsert.call_args.args[0][0]
                self.assertNotIn('1970', raw['last_checked_at'])
                self.assertNotIn('\x00', raw['content'])
                pairs = vector_store.return_value.add_chunks_batch.call_args.args[0]
                for chunk, meta in pairs:
                    self.assertNotIn('\x00', chunk.content)
                    self.assertNotIn(r'\u0000', json.dumps(meta, ensure_ascii=False))
                    self.assertEqual(meta['content_hash'], hashlib.sha256(raw['content'].encode()).hexdigest())
            saved = frontier.rows("url=?", (url,))[0]
            self.assertIsNotNone(saved['indexed_at'])
            self.assertNotIn('\x00', saved['content'])
            frontier.db.close()

    def test_failed_vector_write_preserves_the_previous_published_page(self):
        from crawler.site_sync import index_fetched
        content = '공식 자료의 지원 대상과 신청 방법을 확인할 수 있습니다. ' * 4
        with tempfile.TemporaryDirectory() as temp:
            frontier = Frontier(Path(temp) / 'state.sqlite3')
            url = 'https://www.saha.go.kr/portal/contents.do?mId=example'
            frontier.add(url)
            frontier.update(url, status='fetched', title='공식 지원 안내', content=content,
                            checked_at='2026-10-09T00:00:00+00:00')
            frontier.report = Mock()
            with patch('database_db.database.Database') as database, patch('database_db.vector_store.VectorStore') as vector_store:
                db = database.return_value
                db.get_all_urls.return_value = {url}
                vector_store.return_value.add_chunks_batch.side_effect = TimeoutError('temporary')
                with self.assertRaises(TimeoutError):
                    index_fetched(frontier)
                db.client.table.return_value.upsert.assert_not_called()
                db.client.table.return_value.update.assert_not_called()
                self.assertIsNone(frontier.rows('url=?', (url,))[0]['indexed_at'])
            frontier.db.close()

    def test_business_sections_keep_table_headers_and_exceptions(self):
        sections = extract_sections('<main><h3>사업 A</h3><table><tr><th>대상</th><th>금액</th></tr>'
                                    '<tr><td>첫째</td><td>200만원</td></tr></table><p>단, 지역 조건 적용</p>'
                                    '<h3>사업 B</h3><p>다른 지원입니다.</p></main>')
        self.assertEqual(len(sections), 2)
        self.assertIn('대상 | 금액', sections[0]['text'])
        self.assertIn('첫째 | 200만원', sections[0]['text'])
        self.assertIn('지역 조건', sections[0]['text'])
        self.assertNotIn('다른 지원', sections[0]['text'])

    def test_specific_support_does_not_trigger_generic_audience_question(self):
        from chatbot.response_helpers import build_clarification
        for question in ('고위험 임산부 의료비는 얼마나 지원받을 수 있나요?',
                         '청소년부모 가정은 어떤 지원을 받을 수 있나요?'):
            self.assertIsNone(build_clarification(question))

    def test_navigation_question_is_not_a_physical_address_request(self):
        from chatbot.question_intent import asks_location, asks_navigation
        self.assertTrue(asks_navigation('자전거도로는 어디에서 확인할 수 있나요?'))
        self.assertFalse(asks_location('자전거도로는 어디에서 확인할 수 있나요?'))
        self.assertTrue(asks_location('도서관 위치가 어디인가요?'))
    def test_robots_wildcard_actually_blocks_boards(self):
        rules = RobotsRules('User-agent:*\nDisallow:/*/frame/\nDisallow: /cert/\nDisallow: /*bbs*')
        self.assertFalse(rules.allowed('https://www.saha.go.kr/portal/bbs/list.do?mId=1'))
        self.assertFalse(rules.allowed('https://www.saha.go.kr/health/frame/map.do'))
        self.assertTrue(rules.allowed('https://www.saha.go.kr/health/contents.do?mId=1'))

    def test_more_specific_allow_wins(self):
        rules = RobotsRules('User-agent:*\nDisallow:/docs/\nAllow:/docs/public$')
        self.assertTrue(rules.allowed('https://www.saha.go.kr/docs/public'))
        self.assertFalse(rules.allowed('https://www.saha.go.kr/docs/public/private'))

    def test_official_scope_and_deduplication(self):
        self.assertIsNone(canonical_url('https://www.saha.go.kr:invalid/'))
        self.assertIsNone(canonical_url('https://[broken/'))
        self.assertIsNone(canonical_url('https://saha.go.kr.evil.example/'))
        self.assertIsNone(canonical_url('https://x:s@saha.go.kr/'))
        self.assertIsNone(canonical_url('https://www.saha.go.kr:9999/'))
        self.assertEqual(canonical_url('http://saha.go.kr/health/?b=2&a=1#x'),
                         'https://www.saha.go.kr/health/?a=1&b=2')
        self.assertEqual(canonical_url('/news/view.do?nIdx=5&curHo=8&pageIndex=9'),
                         'https://www.saha.go.kr/news/view.do?nIdx=5')

    def test_redirect_cannot_bypass_robots(self):
        from crawler.site_sync import get_public
        redirect = Mock(is_redirect=True, headers={'Location': '/portal/bbs/list.do'})
        policy = RobotsRules('User-agent:*\nDisallow:/*bbs*')
        with patch('crawler.site_sync.requests.get', return_value=redirect) as get:
            with self.assertRaisesRegex(ValueError, 'robots_disallow'):
                get_public('https://www.saha.go.kr/main.do', policy_for=lambda url: policy)
        self.assertEqual(get.call_count, 1)
        redirect.close.assert_called_once()

    def test_no_auth_submissions_or_calendar_traps(self):
        self.assertTrue(skip_reason('https://www.saha.go.kr/cert/login.do'))
        self.assertTrue(skip_reason('https://www.saha.go.kr/reserve/save.do'))
        self.assertTrue(skip_reason('https://www.saha.go.kr/reserve/calendar/list.do?month=202610'))
        self.assertIsNone(skip_reason('https://www.saha.go.kr/portal/statistics.do?year=2020'))
        self.assertIsNone(skip_reason('https://www.saha.go.kr/tour/contents.do?mId=1'))

    def test_link_discovery_precedes_destructive_content_extraction(self):
        crawler = object.__new__(SahaCrawler)
        page = crawler.parse_page('<nav><a href="/tour/main.do">관광</a></nav><main>내용</main>',
                                  'https://www.saha.go.kr/main.do','공식홈페이지')
        self.assertIn('https://www.saha.go.kr/tour/main.do', page.links)
        self.assertNotIn('관광', page.content)

    def test_categories_keep_sibling_sites_distinct(self):
        self.assertEqual(site_category('https://www.saha.go.kr/health/contents.do?mId=0400000000'), '보건소')
        self.assertEqual(site_category('https://www.saha.go.kr/tour/main.do'), '문화관광')
        self.assertEqual(site_category('https://www.saha.go.kr/portal/contents.do?mId=0501000000'), '사하복지')

    def test_frontier_survives_restart_and_resets_without_deleting_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'state.sqlite3'
            first = Frontier(path)
            first.add('/tour/main.do'); first.add('/cert/login.do')
            first.update('https://www.saha.go.kr/tour/main.do', status='failed', reason='timeout')
            first.db.commit(); first.db.close()
            second = Frontier(path)
            self.assertEqual(len(second.rows("status='failed'")), 1)
            second.reset()
            self.assertEqual(len(second.rows("status='pending'")), 1)
            self.assertEqual(len(second.rows("status='excluded'")), 1)
            second.db.close()

if __name__ == '__main__':
    unittest.main()
