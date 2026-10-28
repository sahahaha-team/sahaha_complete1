import unittest
from unittest.mock import patch

from chatbot.event_grounding import event_years, event_source_time
from chatbot.evidence import is_time_compatible, is_service_source, is_official_document
from chatbot.query_subject import normalize_query, fallback_keywords
from chatbot.response_helpers import build_contextual_search_query
from chatbot.structured_answers import field_matches, structured_brief
from crawler.partner_event import event_calendar_content

URL = 'https://www.busan.go.kr/eng/bsevents/1757816'
TITLE = '제16회 감천문화마을 골목축제'
BODY = '## ' + TITLE + '\n기간: 2026-10-31 (Sat) ~ 2026-11-01 (Sun)\n행사시간: 10:00-18:00\n장소: 감천문화마을 일원'


class EventGroundingTests(unittest.TestCase):
    def test_exchange_visit_is_not_event_schedule_even_with_current_year_elsewhere(self):
        body = ('## 전남광주통합특별시 함평군\n### 교류실적\n'
                '2024. 10. 25. : 제14회 감천문화마을 골목축제 방문(부군수외3명)\n'
                '2026. 04.24. 제28회 함평나비대축제 방문(부구청장 외 4명)')
        doc = {'content': body, 'metadata': {'title': '전남광주통합특별시 함평군'}}
        for query in ('감천문화마을 축제 언제해', '26년 감천문화마을 축제 언제냐고', '2026년 감천문화마을 축제 언제야'):
            with self.subTest(query=query):
                self.assertFalse(is_time_compatible(query, doc))
                self.assertFalse(is_service_source(query, doc, {'감천문화마을'}))
        self.assertTrue(is_service_source('감천문화마을 축제 방문 교류실적', doc, set()))

    def test_short_year_is_a_time_constraint_not_a_required_topic_word(self):
        self.assertIn('2026년', normalize_query('26년 감천문화마을 축제 언제냐고'))
        self.assertNotIn('2026년', fallback_keywords('26년 감천문화마을 축제 언제해'))
        self.assertEqual(event_years('26년 감천문화마을 축제 언제야'), {2026})
        self.assertIn('26년째', normalize_query('26년째 이어온 축제'))

    def test_current_event_requires_current_period_not_recent_check_or_generic_month(self):
        self.assertEqual(event_years('축제 언제해', current_year=2026), {2026})
        self.assertEqual(event_years('내년 축제 일정', current_year=2026), {2027})
        with patch('chatbot.event_grounding.event_years', return_value={2026}):
            self.assertFalse(event_source_time('감천문화마을 축제 언제해', TITLE,
                '## '+TITLE+'\n기간: 2024.10.25~10.27\n확인일: 2026.10.27'))
            self.assertFalse(event_source_time('감천문화마을 축제 언제해', TITLE,
                '## '+TITLE+'\n기간: 매년 10월 중'))
            self.assertTrue(event_source_time('감천문화마을 축제 언제해', TITLE, BODY))

    def test_explicit_old_event_still_works_and_other_year_never_borrows_current_date(self):
        doc = {'content': BODY, 'metadata': {'title': TITLE}}
        self.assertTrue(is_time_compatible('2026년 감천문화마을 축제 일정', doc))
        self.assertFalse(is_time_compatible('2027년 감천문화마을 축제 일정', doc))
        self.assertTrue(is_time_compatible('2024년 감천문화마을 축제 일정', {
            'content': BODY.replace('2026', '2024'), 'metadata': {'title': TITLE}}))
        mixed = BODY.replace('2026', '2024')+'\n## 다른 행사\n기간: 2026.10.31~11.1'
        self.assertFalse(is_time_compatible('2026년 감천문화마을 축제 일정', {
            'content': mixed, 'metadata': {'title': '행사안내'}}))
        self.assertFalse(is_time_compatible('2026년 감천문화마을 축제 시간', {
            'content': '## 2026년 감천문화마을 골목축제\n기간: 2024.10.25~10.27\n행사시간: 10:00-18:00',
            'metadata': {'title': '2026년 감천문화마을 골목축제'}}))

    def test_bare_year_correction_and_following_field_keep_event_and_new_year(self):
        history = [{'role': 'user', 'content': '2024년 감천문화마을 축제 언제해'}]
        corrected = build_contextual_search_query('아니 26년 거 말하는거야', history)
        self.assertIn('감천문화마을', corrected)
        self.assertNotIn('2024년', corrected)
        self.assertEqual(event_years(corrected), {2026})
        field = build_contextual_search_query('그럼 시간은?', [{'role':'user','content':corrected}])
        self.assertIn('감천문화마을', field)
        self.assertEqual(event_years(field), {2026})
        self.assertEqual(build_contextual_search_query('26년', []), '26년')
        self.assertEqual(build_contextual_search_query('여권 준비물', history), '여권 준비물')
        relative = build_contextual_search_query('그럼 시간은?',
            [{'role':'user','content':'내년 감천문화마을 축제 일정'}])
        self.assertEqual(event_years(relative), event_years('내년 감천문화마을 축제 일정'))
        implicit = build_contextual_search_query('어디서 해?',
            [{'role':'user','content':'감천문화마을 축제 언제해'}])
        self.assertEqual(event_years(implicit), event_years('감천문화마을 축제 언제해'))

    def test_final_field_does_not_select_old_date_from_mixed_years(self):
        query = '2026년 감천문화마을 축제 일정'
        self.assertFalse(field_matches('schedule', '기간: 2024.10.25~10.27', query))
        self.assertTrue(field_matches('schedule', BODY.splitlines()[1], query))
        result = structured_brief(query, {'content':BODY, 'metadata':{'title':TITLE}}, BODY, {'감천문화마을'})
        self.assertIsNotNone(result)
        self.assertIn('2026-10-31', result['answer'])

    def test_event_time_and_place_followups_select_the_requested_field(self):
        from chatbot.answer_goal import answer_goal
        doc = {'content':BODY, 'metadata':{'title':TITLE}}
        previous = '감천문화마을 축제 언제해'
        for reply, goal, value, excluded in (
            ('그럼 시간은?', 'hours', '10:00-18:00', '장소:'),
            ('어디서 해?', 'location', '감천문화마을 일원', '행사시간:')):
            query = build_contextual_search_query(reply,[{'role':'user','content':previous}])
            self.assertEqual(answer_goal(query),goal)
            result = structured_brief(query,doc,BODY,{'감천문화마을'})
            self.assertIsNotNone(result)
            self.assertIn(value,result['answer'])
            self.assertNotIn(excluded,result['answer'])

    def test_partner_trust_is_exact_reviewed_url_not_whole_domain(self):
        self.assertTrue(is_official_document({'metadata': {'url':URL}}))
        for url in (URL+'/other', URL+'?arbitrary=1', URL.replace('www.busan.go.kr','www.busan.go.kr.evil.test'),
                    URL.replace('https:', 'http:'), 'https://example.test/'):
            self.assertFalse(is_official_document({'metadata': {'url':url}}))

    def test_partner_calendar_uses_labelled_body_and_poster_alt(self):
        html = ('<div>2027-01-01 navigation</div><div class="boardView">'
                '<h4 class="form-data-subject">Festival</h4><dl class="form-data-info">'
                '<dt>Period</dt><dd>2026-10-31 (Sat) ~ 2026-11-01 (Sun)</dd></dl>'
                '<div class="se-contents"><img alt="제16회 감천문화마을 골목축제 2일간 감천문화마을 일원">'
                '<p>○ Hours: 10:00-18:00</p><p>○ Venue: Gamcheon Culture Village</p></div></div>')
        parsed = event_calendar_content(html)
        self.assertIn(TITLE, parsed)
        self.assertIn('기간: 2026-10-31', parsed)
        self.assertIn('행사시간: 10:00-18:00', parsed)
        self.assertNotIn('2027', parsed)
        with self.assertRaises(ValueError): event_calendar_content('<html>unavailable</html>')

    def test_actual_calendar_fixture_keeps_only_its_event_fields(self):
        from pathlib import Path
        html = (Path(__file__).parent/'fixtures/busan_event_calendar_20261027.html').read_text(encoding='utf8')
        text = event_calendar_content(html)
        self.assertIn('기간: 2026-10-31 (Sat) ~ 2026-11-01 (Sun)',text)
        self.assertIn('장소: 감천문화마을 일원',text)
        self.assertNotIn('장소: 일간',text)
        self.assertNotIn('저작권',text)
        from crawler.saha_crawler import PageData
        from processor.data_cleaner import DataCleaner
        chunks = DataCleaner().process(PageData(url=URL, title=TITLE,
            content=text, category='문화관광', raw_html=html))
        self.assertTrue(chunks)
        self.assertIn('2026-10-31', chunks[0].content)
        self.assertIn(TITLE, chunks[0].content)

    def test_board_detail_links_are_reconstructed_without_executing_script(self):
        from bs4 import BeautifulSoup
        from crawler.saha_crawler import SahaCrawler
        html = '''<form id="listForm" action="/portal/bbs/list.do?ptIdx=24&mId=0301060000">
        <a href="#" onclick="boardView('listForm', 'writer', 'Y', '155099', '24', '0301060000', '1'); return false;">공고</a>
        <a href="#" onclick="alert('not executed')">무효</a></form>'''
        links = object.__new__(SahaCrawler)._extract_links(BeautifulSoup(html,'lxml'),
            'https://www.saha.go.kr/portal/contents.do?mId=0301060000')
        self.assertEqual(links, ['https://www.saha.go.kr/portal/bbs/view.do?bIdx=155099&ptIdx=24&mId=0301060000'])
