import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from chatbot.facility_contact import facility_contact


class FacilityContactTests(unittest.TestCase):
    def row(self, body, days=0):
        return {'title': '이용안내', 'content': body, 'raw_html': '',
                'last_checked_at': (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()}

    def test_only_current_explicit_unambiguous_phone_is_returned(self):
        with patch('database_db.raw_pages.read_raw_pages', return_value=[self.row('전화번호: 051-271-6835')]):
            result = facility_contact('소방특화 들락날락 전화번호', object())
            self.assertIn('051-271-6835', result['answer'])
            self.assertIn('mId=1207000000', result['sources'][0]['url'])

    def test_stale_ambiguous_or_nonphone_number_is_not_published(self):
        for row in (self.row('전화번호: 051-271-6835', 8),
                    self.row('전화번호: 051-271-6835\n전화번호: 051-220-1111'),
                    self.row('예약번호: 051-271-6835')):
            with patch('database_db.raw_pages.read_raw_pages', return_value=[row]):
                self.assertIsNone(facility_contact('소방특화 들락날락 전화번호', object()))

    def test_department_fax_and_application_method_do_not_use_facility_phone(self):
        for query in ('소방특화 담당부서 전화번호', '소방특화 팩스번호', '소방특화 전화로만 예약하나요?'):
            with patch('database_db.raw_pages.read_raw_pages') as read:
                self.assertIsNone(facility_contact(query, object()))
                read.assert_not_called()
