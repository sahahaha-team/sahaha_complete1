import re
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from chatbot.conversation import ChatBot
from chatbot.contact_directory import ContactDirectoryResponder
from chatbot.response_helpers import build_clarification, resolve_clarification_reply
from chatbot.verified_facts import (
    parse_council_location, parse_kiosk_location, parse_online_resident_copy,
    parse_kiosk_resident_copy, answer_verified_table_question,
)


COUNCIL = "구청오시는 길\n주소 및 전화 안내\n주소 : 부산광역시 사하구 예시로 12\n대표전화 : 051-220-1234 / Fax : 051-220-9999\n교통편 안내\n"
KIOSK = ("설치장소 및 운영시간\n사하구청 본관\n(민원실)\n1\n24시간\n부산 사하구\n"
         "예시로 12\n(당리동)\n부동산등기부등본 및\n가족관계증명\n발급가능\n사하구청 본관우측\n"
         "옥외부스\n1\n09:00~18:00\n부산 사하구\n다른길 99\n(당리동)\n주민등록등본\n"
         "발급받고자 하는 증명종류 선택 → 주민번호 입력 → 본인 지문 확인 → 자료처리 → 수수료 투입 → 증명서 발급\n"
         "※ 주민등록증의 지문과 다르게 인식되는 경우 관할 동행정복지센터에서 발급받으시기 바랍니다.")
ONLINE = "정부24 민원서비스\n주민등록 등·초본\n인터넷을 이용해 신청·열람·발급\n실명인증"


class ServiceNavigationTests(unittest.TestCase):
    def test_actual_welcome_buttons_open_choices_without_retrieval(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / 'templates/index.html').read_text(encoding='utf-8')
        buttons = re.findall(r'class="quick-btn service-btn" data-msg="([^"]+)"', html)
        self.assertEqual(len(buttons), 4)
        bot = object.__new__(ChatBot)
        bot.db, bot._memory_history, bot._history_lock, bot.retriever = None, {}, threading.RLock(), Mock()
        for message in buttons:
            with self.subTest(message=message):
                result = bot.chat(message, message)
                self.assertTrue(result['is_clarification'])
                self.assertEqual(len(result['suggested_questions']), 3)
                self.assertFalse(result['degraded'])
                self.assertEqual(result['sources'], [])
        bot.retriever.search.assert_not_called()
        bot.retriever.search_official_url.assert_not_called()

    def test_short_choices_become_full_questions_and_category_changes_stay_separate(self):
        for query, reply, expected in (
            ('구청 안내해줘', '위치', '사하구청 위치 알려줘'),
            ('복지 서비스 안내해줘', '어르신', '어르신 복지 지원 알려줘'),
            ('민원 안내해줘', '등본', '주민등록등본 발급 방법 알려줘'),
            ('생활환경 안내해줘', '대형', '대형폐기물 배출 방법 알려줘'),
        ):
            pending = {'query': query, **build_clarification(query)}
            self.assertEqual(resolve_clarification_reply(reply, pending), expected)
            self.assertEqual(resolve_clarification_reply('민원 안내해줘', pending), '민원 안내해줘')
            for question in pending['suggested_questions']:
                self.assertEqual(resolve_clarification_reply(question, pending), question)

    def test_resident_copy_asks_channel_instead_of_repeating_method(self):
        query = '주민등록등본 발급 방법 알려줘'
        pending = {'query': query, **build_clarification(query)}
        self.assertIn('온라인', pending['answer'])
        for reply in ('온라인', '무인민원발급기'):
            resolved = resolve_clarification_reply(reply, pending)
            self.assertIsNone(build_clarification(resolved))
            client = Mock()
            client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                {'content': ONLINE if reply == '온라인' else KIOSK, 'last_checked_at': datetime.now(timezone.utc).isoformat()}]
            self.assertTrue(answer_verified_table_question(resolved, client)['verified'])

    def test_child_support_choices_do_not_offer_child_employment(self):
        result = build_clarification('아동·보육 지원 알려줘')
        self.assertIn('부모급여', result['answer'])
        self.assertNotIn('일자리', ' '.join(result['suggested_questions']))

    def test_mixed_council_location_contact_does_not_become_a_staff_duty(self):
        responder = ContactDirectoryResponder()
        with patch.object(responder, '_load', side_effect=AssertionError('Wrong contact path')):
            self.assertIsNone(responder.respond('s', '사하구청 위치와 연락처 알려줘'))

    def test_council_uses_verified_address_and_representative_not_fax(self):
        result = parse_council_location(COUNCIL)
        self.assertIn('예시로 12', result)
        self.assertIn('051-220-1234', result)
        self.assertNotIn('9999', result)
        self.assertIsNone(parse_council_location(COUNCIL.replace('대표전화 :', '팩스 :')))

    def test_kiosk_row_does_not_borrow_next_facility_values(self):
        result = parse_kiosk_location(KIOSK)
        self.assertIn('24시간', result)
        self.assertIn('예시로 12', result)
        self.assertNotIn('다른길', result)
        self.assertNotIn('09:00', result)
        self.assertIsNone(parse_kiosk_location(KIOSK.replace('24시간\n', '', 1)))
        self.assertIsNone(parse_kiosk_location(KIOSK.replace('24시간\n', '24시간\n주말 미운영\n', 1)))

    def test_resident_copy_does_not_infer_unmentioned_document_or_omit_fingerprint_exception(self):
        self.assertIn('정부24', parse_online_resident_copy(ONLINE))
        self.assertIsNone(parse_online_resident_copy(ONLINE.replace('주민등록 등·초본', '자동차등록원부')))
        self.assertIn('관할 동행정복지센터', parse_kiosk_resident_copy(KIOSK))
        self.assertIsNone(parse_kiosk_resident_copy(KIOSK.replace('주민등록등본', '부동산등기부등본')))

    def test_old_building_source_cannot_be_marked_verified(self):
        client = Mock()
        client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {'content': COUNCIL, 'last_checked_at': (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()}]
        result = answer_verified_table_question('사하구청 위치와 연락처 알려줘', client)
        self.assertFalse(result['verified'])
        self.assertEqual(result['sources'], [])
        for query in ('사하구청 제2청사 위치 알려줘', '건축과 위치와 연락처 알려줘', '다대도서관 무인민원발급기 위치 알려줘', '대리인 주민등록등본 온라인 발급 방법 알려줘'):
            self.assertIsNone(answer_verified_table_question(query, client), query)


if __name__ == '__main__':
    unittest.main()
