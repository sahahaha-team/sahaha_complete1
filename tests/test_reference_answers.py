import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from chatbot.answer_goal import answer_goal
from chatbot.concise_answers import concise_source_answer
from chatbot.grounded_planner import answer_with_grounded_model, eligible_ids, render_plan
from chatbot.query_subject import query_keywords
from chatbot.reference_answers import reference_answer
from chatbot.source_answers import strip_page_chrome, build_source_answer
from database_db.database import Database
from scripts.ingest_official_materials import _fetch_page, _index_page

URL = 'https://www.saha.go.kr/portal/contents.do?mId=0403020000'
FILE = 'https://www.saha.go.kr/portal/Downfiles/saha_bicycle_road2017.pdf'
BODY = '사하구 자전거 도로 현황도\n아름다운 사하의 석양과 갈맷길을 따라 바람을 가르는 자전거 도로!\n자전거도로 자세히보기'
QUERY = '사하구 자전거도로는 어디에서 확인할 수 있나요?'
ATTACHMENTS = [{'name': '자전거도로 자세히보기', 'url': FILE}]


def document(title='자전거 도로 현황도', body=BODY, url=URL, attachments=None):
    return {'content': body, 'metadata': {'title': title, 'url': url,
            'source_type': 'crawled_page', 'attachments': ATTACHMENTS if attachments is None else attachments}}


class ReferenceAnswerTests(unittest.TestCase):
    def test_where_to_check_is_navigation_but_clinic_and_course_are_places(self):
        for q in (QUERY, '자전거도로 지도 어디서 볼 수 있어?', '자전거도로 현황도 링크 알려줘'):
            self.assertEqual(answer_goal(q), 'reference')
        self.assertEqual(answer_goal('백신 접종 어디서 해'), 'location')
        self.assertEqual(answer_goal('소방 안전 교육 어디서 들어'), 'location')

    def test_navigation_has_subject_without_requiring_word_map_in_body(self):
        self.assertEqual(query_keywords('자전거도로 지도 어디에서 확인해?', ['자전거', '도로', '지도', '확인']), {'자전거', '도로'})
        self.assertEqual(query_keywords('지도 어디에서 확인해?', ['지도', '확인']), {'지도'})

    def test_model_cannot_choose_promotion_for_reference_question(self):
        packet = {'units': BODY.splitlines()}
        self.assertNotIn(1, eligible_ids(QUERY, packet, {'자전거', '도로'}))
        packet.update(body=BODY, document=document())
        self.assertIsNone(render_plan(QUERY, {'mode':'answer', 'source':0, 'units':[1]}, [packet], {'자전거','도로'}))
        llm = Mock()
        r = answer_with_grounded_model(QUERY, [document()], None, {'자전거', '도로'}, llm)
        self.assertIn(URL, r['answer'])
        self.assertIn(FILE, r['answer'])
        self.assertEqual(r['answer_method'], 'official_reference')
        self.assertNotIn('아름다운', r['answer'])
        llm.model_copy.assert_not_called()

    def test_dated_map_filename_does_not_establish_current_lengths(self):
        r = reference_answer(QUERY, document(), BODY, {'자전거', '도로'})
        self.assertIn('파일명에 **2017**', r['answer'])
        self.assertIn('최신 변경 사항', r['answer'])
        self.assertNotIn('km', r['answer'])
        self.assertNotIn('작성일', r['answer'])
        self.assertLessEqual(len(r['answer']), 480)

    def test_generic_map_question_uses_link_instead_of_promotion(self):
        r = answer_with_grounded_model('자전거도로 알려줘', [document()], None, {'자전거', '도로'}, Mock())
        self.assertIn(FILE, r['answer'])
        self.assertNotIn('아름다운', r['answer'])

    def test_source_only_fallback_provides_same_verified_links(self):
        original = '\n'.join('> ' + line for line in BODY.splitlines())
        r = concise_source_answer(QUERY, original, [document()], {'자전거', '도로'})
        self.assertIn(FILE, r['answer'])
        self.assertEqual(r['answer_details'], original)

    def test_unrelated_body_or_lookalike_domain_cannot_supply_reference(self):
        for d, body in [(document(body='여권 신청 안내'), '여권 신청 안내'),
                        (document(url='https://saha.go.kr.example.com/fake'), BODY)]:
            self.assertIsNone(reference_answer(QUERY, d, body, {'자전거', '도로'}))

    def test_unsafe_attachment_links_are_not_displayed(self):
        for url in ('javascript:alert(1)', 'https://[invalid', 'https://saha.go.kr.example.com/road.pdf',
                    'https://user:secret@www.saha.go.kr/road.pdf', 'https://www.saha.go.kr/road.pdf)'):
            r = reference_answer(QUERY, document(attachments=[{'url': url}]), BODY, {'자전거', '도로'})
            self.assertNotIn(url, r['answer'])

    def test_navigation_is_general_and_does_not_require_a_pdf(self):
        body = '사하구 공영주차장 안내\n공영주차장 목록을 확인하세요.'
        url = 'https://www.saha.go.kr/portal/contents.do?mId=parking'
        r = reference_answer('공영주차장 목록 어디에서 확인해?',
            document('공영주차장 안내', body, url, []), body, {'공영주차장'})
        self.assertIn(url, r['answer'])
        self.assertNotIn('2017', r['answer'])

    def test_quote_retains_source_text_without_standalone_icon_and_escape_noise(self):
        text = 'Home\n인쇄하기\nsvg\n>\n\\\n자전거 도로 현황도\n자전거도로 자세히보기\n만족도조사\n5점'
        self.assertEqual(strip_page_chrome(text), '자전거 도로 현황도\n자전거도로 자세히보기')

    def test_chunk_metadata_is_hydrated_from_original_with_attachment(self):
        d = document(attachments=[])
        d['metadata']['source_type'] = 'verified_page'
        client = Mock()
        client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {'content': BODY, 'attachments': ATTACHMENTS}]
        llm = Mock()
        r = answer_with_grounded_model(QUERY, [d], client, {'자전거', '도로'}, llm)
        self.assertIn(FILE, r['answer'])
        self.assertEqual(r['documents'][0]['metadata']['attachments'], ATTACHMENTS)

    def test_source_only_map_location_can_answer_without_an_address_field(self):
        client = Mock()
        client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {'content': BODY, 'attachments': ATTACHMENTS}]
        q = '자전거도로 어디야?'
        original, used = build_source_answer([document()], client, query=q,
                                            topic_keywords={'자전거','도로'}, require_brief=True)
        self.assertTrue(original)
        r = concise_source_answer(q, original, used, {'자전거','도로'})
        self.assertIn(FILE, r['answer'])
        self.assertFalse(r['is_clarification'])

    def test_map_navigation_does_not_replace_a_request_for_hours_or_cost(self):
        for q in ('자전거도로 이용시간 알려줘', '자전거도로 이용비용 얼마야'):
            self.assertIsNone(reference_answer(q, document(), BODY, {'자전거','도로'}))

    def test_declining_a_link_does_not_override_the_requested_answer_field(self):
        self.assertEqual(answer_goal('보건소 운영시간만 알려줘 링크는 필요없어'), 'hours')
        self.assertEqual(answer_goal('여권 링크 말고 비용 얼마야'), 'cost')


class AttachmentPersistenceTests(unittest.TestCase):
    def db(self, attachments):
        db = Database.__new__(Database)
        db.client = Mock()
        db.client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {'id': 'existing', 'title': '자전거 도로 현황도',
             'content_hash': hashlib.md5(BODY.encode()).hexdigest(), 'attachments': attachments}]
        return db

    def page(self, attachments):
        return SimpleNamespace(url=URL, title='자전거 도로 현황도', content=BODY,
                               sub_category='교통', attachments=attachments)

    def test_new_attachment_updates_even_with_identical_body(self):
        db = self.db([])
        self.assertEqual(db.upsert_raw_page(self.page(ATTACHMENTS)), 'updated')
        self.assertEqual(db.client.table.return_value.update.call_args.args[0]['attachments'], ATTACHMENTS)

    def test_removed_attachment_does_not_remain_as_stale_metadata(self):
        db = self.db(ATTACHMENTS)
        self.assertEqual(db.upsert_raw_page(self.page([])), 'updated')
        self.assertEqual(db.client.table.return_value.update.call_args.args[0]['attachments'], [])

    def test_identical_body_and_attachment_skip_reindexing(self):
        db = self.db(ATTACHMENTS)
        self.assertEqual(db.upsert_raw_page(self.page(ATTACHMENTS)), 'unchanged')
        db.client.table.return_value.update.assert_not_called()

    @patch('scripts.ingest_official_materials.requests.get')
    def test_official_refresh_collects_pdf_instead_of_erasing_attachments(self, get):
        get.return_value = SimpleNamespace(url=URL, apparent_encoding='utf-8',
            text=f'<title>자전거 도로 현황도</title><main>{BODY * 2}<a href="{FILE}">자전거도로 자세히보기</a></main>',
            raise_for_status=lambda: None)
        row = _fetch_page((QUERY, URL))
        self.assertEqual(row['attachments'], ATTACHMENTS)

    def test_import_passes_attachments_to_raw_chunks_and_vector_metadata(self):
        db, vs = Mock(), Mock()
        db.upsert_raw_page.return_value = 'updated'
        db.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        db.client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        row = {'source_type': 'verified_page', 'url': URL, 'title': '자전거 도로 현황도',
               'content': BODY * 2, 'category': '분야별정보', 'checked_at': '2026-10-10', 'attachments': ATTACHMENTS}
        self.assertGreater(_index_page(db, vs, row), 0)
        self.assertEqual(db.upsert_raw_page.call_args.args[0].attachments, ATTACHMENTS)
        self.assertEqual(db.save_chunks_bulk.call_args.args[0][0][0].attachments, ATTACHMENTS)
        self.assertEqual(vs.add_chunks_batch.call_args.args[0][0][1]['attachments'], ATTACHMENTS)


if __name__ == '__main__':
    unittest.main()
