"""Team FAQ/HTML additions must preserve the current official-evidence routes."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from chatbot.contact_directory import ContactDirectoryResponder
from chatbot.faq_targets import find_official_question
from chatbot.retriever import HybridRetriever
from crawler.saha_crawler import SahaCrawler
from database_db.database import Database
from processor.data_cleaner import DataCleaner
from chatbot.query_subject import fallback_keywords
from chatbot.evidence import is_official_document, topic_support, is_answerable_document
from chatbot.official_faq import OfficialFAQIndex
from chatbot.question_intent import asks_location
from chatbot.concise_answers import course_scope_result


class MergeIntegrationTests(unittest.TestCase):
    def test_faq_alias_selects_current_original_instead_of_draft_answer(self):
        query = '작은도서관 교육 프로그램 예약 방법 알려줘'
        match = find_official_question(query)
        self.assertIn('0408030000', match['url'])
        original = {'content': '현재 원문에서 확인한 도서관 예약 안내',
                    'metadata': {'url': match['url'], 'title': '도서관'}}
        retriever = object.__new__(HybridRetriever)
        retriever.bm25 = None
        retriever.page_index = MagicMock()
        retriever.page_index.search.return_value = [original]
        result = retriever.search(query)
        self.assertEqual(result['results'], [original])
        self.assertNotIn('approved_answer', result['results'][0]['metadata'])
        self.assertEqual(retriever.page_index.search.call_args.kwargs['url'], match['url'])

    def test_original_table_text_and_structured_search_chunks_coexist(self):
        crawler = object.__new__(SahaCrawler)
        html = '''<main><h2>성인 예방접종</h2>
        <p>접종 대상별 시간이 다르므로 대상 조건을 확인하고 방문하시기 바랍니다.</p>
        <table><tr><th>구분</th><th>시간</th></tr>
        <tr><td>오전</td><td>09:00~11:30</td></tr></table></main>'''
        page = crawler.parse_page(html, 'https://www.saha.go.kr/health/test', '보건소')
        self.assertIn('오전\n09:00~11:30', page.content)
        original = page.content
        chunks = DataCleaner().process(page)
        self.assertEqual(page.content, original)
        self.assertTrue(any('문서 위치: 성인 예방접종' in chunk.content for chunk in chunks))
        self.assertTrue(any('표 | 오전 | 09:00~11:30' in chunk.content for chunk in chunks))

    def test_missing_html_column_falls_back_without_hiding_other_errors(self):
        db = object.__new__(Database)
        db.client = MagicMock()
        db.client.table.return_value.insert.return_value.execute.side_effect = [
            RuntimeError('raw_html column missing from schema cache'), SimpleNamespace(data=[{}])]
        db._write_raw_page('insert', {'content': '원문', 'raw_html': '<main>원문</main>'})
        last_payload = db.client.table.return_value.insert.call_args.args[0]
        self.assertEqual(last_payload, {'content': '원문'})
        self.assertFalse(db._raw_html_supported)
        db.client.table.return_value.insert.return_value.execute.side_effect = RuntimeError('permission denied')
        with self.assertRaisesRegex(RuntimeError, 'permission denied'):
            db._write_raw_page('insert', {'content': '원문', 'raw_html': '<main>원문</main>'})

    def test_text_only_refresh_does_not_erase_saved_html(self):
        db = object.__new__(Database)
        self.assertEqual(db._with_raw_html({}, SimpleNamespace(raw_html='')), {})

    def test_compound_office_question_reaches_original_page_route(self):
        responder = ContactDirectoryResponder()
        with patch.object(responder, '_load') as load:
            self.assertIsNone(responder.respond('merge', '사하구청 위치와 연락처 알려줘'))
            load.assert_not_called()

    def test_compound_location_keeps_facility_instead_of_generic_location_word(self):
        query = '사하구청 위치와 연락처 알려줘'
        self.assertTrue(asks_location(query))
        self.assertEqual(fallback_keywords(query), {'구청'})

    def test_library_program_cannot_borrow_smoking_education_instructions(self):
        keywords = fallback_keywords('작은도서관 교육 프로그램 예약 방법 알려줘')
        self.assertIn('작은도서관', keywords)
        self.assertFalse(topic_support({'content': '학교별 금연교육 프로그램 예약 신청 안내'}, keywords)[0])

    def test_general_resident_course_does_not_repeat_an_audience_question(self):
        self.assertIsNone(course_scope_result('작은도서관 교육 프로그램 예약 방법', '대상: 사하구민'))
        self.assertIsNotNone(course_scope_result('소방 안전 교육 어디서 들어', '대상: 공동주택 경비책임자'))

    def test_faq_draft_is_not_official_evidence_just_because_it_has_an_official_url(self):
        docs = OfficialFAQIndex().search_documents('사하구청 대표전화 알려줘', limit=1)
        self.assertTrue(docs)
        self.assertFalse(is_official_document(docs[0]))

    def test_priority_sources_are_refreshed_without_a_private_workbook(self):
        from scripts.ingest_official_materials import official_page_targets
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as directory:
            targets = official_page_targets(Path(directory))
        self.assertTrue(any('0408030000' in url for _, url in targets))
        self.assertEqual(len(targets), len({url for _, url in targets}))

    def test_new_catalogue_landing_pages_are_not_specific_service_instructions(self):
        for url in ('https://www.saha.go.kr/welfare.do', 'https://www.saha.go.kr/reserve/main.do'):
            self.assertFalse(is_answerable_document('프로그램 신청 방법', {'metadata': {'url': url}, 'content': '홈페이지 메뉴 목록'}))


if __name__ == '__main__':
    unittest.main()
