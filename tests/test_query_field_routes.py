import json
import unittest
from pathlib import Path

from chatbot.answer_goal import answer_goal, requested_goals
from chatbot.contact_directory import ContactDirectoryResponder
from chatbot.query_subject import interpret_query, service_names
from chatbot.response_helpers import unavailable_capability
from chatbot.structured_answers import structured_brief

FIXTURES = Path(__file__).parent / 'fixtures'


def source(key):
    return json.loads((FIXTURES / 'accuracy_n_sources_20261016.json').read_text(encoding='utf8'))[key]


def brief(key, question, keywords):
    d = source(key)
    return structured_brief(interpret_query(question), d, d['content'], keywords)


class QueryFieldRouteTests(unittest.TestCase):
    def test_compound_hours_address_keeps_both_facts(self):
        q = '보건소가 몇 시부터 몇 시까지 진료하고 어느 주소에 있나요?'
        r = brief('health', q, {'보건소'})
        self.assertEqual(set(requested_goals(q)), {'hours', 'location'})
        self.assertIn('185', r['answer'])
        self.assertIn('12시~13시', r['answer'])

    def test_short_service_words_are_not_accidental_character_joins(self):
        self.assertNotIn('지진', service_names('몇 시까지 진료하나요?'))
        self.assertNotIn('구인', service_names('청구인에게 통지하나요?'))
        self.assertNotIn('소방', service_names('보건소 방문 시간'))
        self.assertIn('지진', service_names('지진 대피 요령'))
        self.assertIn('구인', service_names('구인 정보 알려줘'))

    def test_filing_deadline_is_not_processing_time(self):
        r = brief('move', '전입 신고할 수 있는 기한이 며칠인지 궁금합니다.', {'전입신고'})
        self.assertIn('14일 이내', r['answer'])
        self.assertNotIn('즉시', r['answer'])

    def test_youth_in_person_reservation_is_not_telephone_program(self):
        r = brief('smoking', '고등학생이 금연 상담받으러 가려면 예약이 있어야 하나요?', {'금연'})
        self.assertFalse(r['is_clarification'])
        self.assertIn('청소년', r['answer'])
        self.assertIn('예약', r['answer'])
        self.assertNotIn('1544-9030', r['answer'])

    def test_free_pickup_contact_is_a_service_channel_not_address(self):
        q = '멀쩡한 냉장고를 돈 안 내고 수거 요청하려면 어디로 연락하나요?'
        self.assertNotIn('location', requested_goals(q))
        r = brief('free', q, {'냉장고', '무상', '수거'})
        self.assertIsNotNone(r)
        self.assertIn('1599-0903', r['answer'])
        self.assertIn('훼손', r['answer'])

    def test_communication_method_does_not_enter_employee_lookup(self):
        q = '마을세무사는 상담을 전화로만 받을 수 있나요?'
        self.assertIsNone(ContactDirectoryResponder().respond('route-regression', q))
        r = brief('tax', q, {'마을세무사'})
        for value in ('팩스', '이메일', '대면'):
            self.assertIn(value, r['answer'])

    def test_labelled_limit_is_complete_but_unfinished_verb_is_not(self):
        from chatbot.answer_completion import source_unit_complete
        d = json.loads((FIXTURES / 'accuracy_m_sources_U009.json').read_text(encoding='utf8'))
        q = '희망도서를 신청만 하고 계속 빌려가지 않으면 신청이 제한되나요?'
        r = structured_brief(q, d, d['content'], {'희망도서'})
        self.assertIn('미대출 3권', r['answer'])
        self.assertIn('2개월', r['answer'])
        self.assertFalse(source_unit_complete('신청조건: 증빙서류를 제출한'))

    def test_pending_court_case_selects_actual_exclusion(self):
        d = json.loads((FIXTURES / 'accuracy_m_sources_U017.json').read_text(encoding='utf8'))
        q = '납세자보호관에게 법원에서 이미 진행 중인 건도 고충민원으로 내도 되나요?'
        r = structured_brief(q, d, d['content'], {'납세자보호관'})
        self.assertIn('제외대상', r['answer'])
        self.assertIn('소송이 진행 중', r['answer'])

    def test_gift_percentage_is_not_tax_deduction(self):
        r = brief('donation', '고향사랑기부 답례품은 기부금의 몇 퍼센트까지 주나요?', {'고향사랑기부'})
        self.assertIn('30%', r['answer'])
        self.assertNotIn('16.5%', r['answer'])

    def test_explicit_applicant_keeps_common_documents_and_own_row(self):
        d = json.loads((FIXTURES / 'accuracy_m_sources_U011.json').read_text(encoding='utf8'))
        q = '조상땅찾기에 상속인이 직접 가면 신분증 말고 어떤 서류를 가져가죠?'
        r = structured_brief(q, d, d['content'], {'조상땅'})
        self.assertIn('제적등본', r['answer'])
        self.assertIn('가족관계증명서', r['answer'])
        self.assertNotIn('위임장', r['answer'])

    def test_decision_extension_keeps_deadline_and_written_notice(self):
        q = '정보공개 결정을 연장할 수도 있나요? 연장하면 청구인에게 알려주나요?'
        r = brief('information', q, {'정보공개'})
        self.assertIn('10일', r['answer'])
        self.assertIn('문서로 통지', r['answer'])
        self.assertNotIn('구술방법', r['answer'])

    def test_current_waiting_count_has_no_fabricated_population(self):
        r = unavailable_capability('지금 영양플러스 신청 대기 인원이 정확히 몇 명인지 알려줘.')
        self.assertEqual(r['degraded_reason'], 'live_data_unavailable')
        self.assertIn('조회하는 기능이 없습니다', r['answer'])
        self.assertIsNone(unavailable_capability('영양플러스 신청 인원 선정기준 알려줘'))


if __name__ == '__main__':
    unittest.main()
