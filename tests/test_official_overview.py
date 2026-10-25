import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from chatbot.official_overview import official_overview


class OfficialOverviewTests(unittest.TestCase):
    def test_tax_catalogue_quotes_its_classification_and_marks_missing_full_list(self):
        row = {'title': '세금의분류', 'raw_html': '',
               'content': '국세 - 소득세 등\n지방세 - 지방자치단체가 부과징수하는 세금(부산광역시세, 자치구세 등)',
               'last_checked_at': datetime.now(timezone.utc).isoformat()}
        with patch('database_db.raw_pages.read_raw_pages', return_value=[row]):
            result = official_overview('사하구 지방세에는 어떤 종류가 있나요?', object())
        self.assertIn('자치구세', result['answer'])
        self.assertNotIn('소득세', result['answer'])
        self.assertEqual(result['evidence']['status'], 'partial')

    def test_reservation_overview_uses_only_declared_official_navigation(self):
        html = '<a id="menu10">가짜 분야</a><ul id="gnb">'
        for number, label in enumerate(['교육·강좌','공연·전시','문화·체험','대여·대관'], 10):
            html += f'<li><a id="menu{number}" href="/reserve/contents.do?mId={number}00000000">{label}</a></li>'
        html += '<li><a id="menu60" href="/reserve/private">나의예약현황</a></li></ul>'
        row = {'title': '통합예약', 'raw_html': html, 'last_checked_at': datetime.now(timezone.utc).isoformat()}
        with patch('database_db.raw_pages.read_raw_pages', return_value=[row]):
            result = official_overview('사하구 통합예약에서는 무엇을 예약할 수 있나요?', object())
        self.assertIn('문화·체험', result['answer'])
        self.assertNotIn('가짜', result['answer'])
        self.assertNotIn('나의예약', result['answer'])

    def test_narrow_question_and_missing_html_do_not_inherit_an_overview(self):
        self.assertIsNone(official_overview('자동차세 납부 기한', object()))
        with patch('database_db.raw_pages.read_raw_pages', return_value=[]):
            self.assertIsNone(official_overview('사하구 통합예약에서는 무엇을 예약할 수 있나요?', object()))
