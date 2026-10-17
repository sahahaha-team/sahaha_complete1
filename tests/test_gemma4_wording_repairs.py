"""Source eligibility, quantities and changed applicant profiles share routing."""
import unittest
from unittest.mock import Mock, patch

from chatbot.answer_goal import answer_goal
from chatbot.evidence_decision import document_decision
from chatbot.grounded_planner import answer_with_grounded_model
from chatbot.passport_documents import applicant_age, applicant_role, parse_passport_documents
from chatbot.query_subject import interpret_query, service_names
from chatbot.response_helpers import (build_clarification, resolve_clarification_reply,
    build_contextual_search_query, unavailable_capability)
from tests.test_passport_documents import HTML
from chatbot.official_content import official_html_text


class WordingRepairsTests(unittest.TestCase):
    def test_ineligible_source_never_runs_deep_field_extraction(self):
        doc = {'content': '## 불법주정차\n신고방법: 안전신문고', 'metadata': {
            'url': 'https://www.saha.go.kr/portal/test', 'title': '불법주정차',
            'source_type': 'crawled_page'}, 'vector_similarity': .99}
        with patch('chatbot.evidence_decision._coverage') as coverage:
            result = document_decision('금연약 복용량', doc, {'금연'})
        coverage.assert_not_called()
        self.assertFalse(result['relevant'])
        self.assertEqual(result['matched_fields'], [])
        self.assertEqual(result['missing_fields'], ['medical_details'])

    def test_eligible_source_still_requires_requested_field(self):
        doc = {'content': '## 금연클리닉\n대상: 금연을 원하는 지역주민', 'metadata': {
            'url': 'https://www.saha.go.kr/health/test', 'title': '금연클리닉',
            'source_type': 'crawled_page'}}
        result = document_decision('금연약 복용량', doc, {'금연'})
        self.assertTrue(result['relevant'])
        self.assertIn('medical_details', result['missing_fields'])

    def test_stated_medication_quantities_are_not_generic_services(self):
        for query in ('금연약을 두 알 먹어도 되나요?', '약을 2정 복용해도 돼?',
                      '니코틴 패치 한 장 붙이면 되나요?', '금연약 한 알 먹어도 되나요?'):
            with self.subTest(query=query):
                self.assertEqual(answer_goal(query), 'medical_details')
        self.assertEqual(answer_goal('금연클리닉 보조제 종류와 지원 내용'), 'services')

    def test_dose_cannot_be_replaced_by_counseling_and_no_model_is_called(self):
        body = '## 금연클리닉\n대상: 금연을 원하는 지역주민\n내용: 금연상담 및 금연보조제 제공'
        doc = {'content': body, '_raw_page': {'content': body}, 'metadata': {
            'url': 'https://www.saha.go.kr/health/test', 'title': '금연클리닉',
            'source_type': 'crawled_page'}}
        llm = Mock()
        result = answer_with_grounded_model('금연약을 두 알 먹어도 되나요?', [doc], None, {'금연'}, llm)
        llm.model_copy.assert_not_called()
        self.assertFalse(result and not result.get('degraded'))

    def test_live_vacancies_and_static_capacity_or_fees_remain_distinct(self):
        for query in ('지금 공영 주차장 남은 칸 알려줘요.', '현재 주차장 여유 공간은?',
                      '실시간 공영주차장 잔여 주차면 알려줘'):
            self.assertEqual(unavailable_capability(query)['degraded_reason'], 'live_data_unavailable')
        for query in ('공영주차장 전체 주차면수 알려줘', '현재 공영주차장 요금은?',
                      '공영주차장 위치 알려줘'):
            self.assertIsNone(unavailable_capability(query))

    def test_book_alias_keeps_specific_service_and_quantity(self):
        for query in ('작은 도서관 희망책은 한달에 몇권 신청해요?',
                      '작은도서관 희망 책 몇 권 신청할 수 있나요?'):
            self.assertIn('희망도서', service_names(query))
            self.assertEqual(answer_goal(query), 'schedule')
        self.assertEqual(interpret_query('책상 안전대책'), '책상 안전대책')

    def test_pending_role_question_can_change_to_adult_renewal(self):
        query = '미성년 자녀 여권을 다시 만들 때 준비할 서류는요?'
        pending = {'query': query, **build_clarification(query)}
        resolved = resolve_clarification_reply('그럼 어른 재발급은요?', pending)
        self.assertEqual(applicant_age(resolved), 'adult')
        self.assertNotIn('미성년', resolved)
        self.assertIn('서류', resolved)
        self.assertIn('기존 여권', parse_passport_documents(resolved, official_html_text(HTML)))
        self.assertEqual(resolve_clarification_reply('공영주차장 요금은?', pending), '공영주차장 요금은?')

    def test_profile_replacement_preserves_new_age_role_and_requested_field(self):
        history = [{'role': 'user', 'content': '성인 신규 여권 준비 서류'}]
        resolved = build_contextual_search_query('그럼 만17세 본인 재발급은요?', history)
        self.assertEqual(applicant_age(resolved), 'minor')
        self.assertEqual(applicant_role(resolved), 'self')
        self.assertNotIn('신규', resolved)
        self.assertIn('17세', resolved)
        self.assertIn('인감증명서', parse_passport_documents(resolved, official_html_text(HTML)))


if __name__ == '__main__':
    unittest.main()
