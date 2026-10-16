import json
import unittest
from pathlib import Path

from chatbot.answer_goal import answer_goal, requested_goals
from chatbot.question_intent import asks_location
from chatbot.structured_answers import structured_brief, field_matches


class ConjunctionAndDeadlineIntentTests(unittest.TestCase):
    @staticmethod
    def document(name):
        path = Path(__file__).parent / 'fixtures/accuracy_n_sources_20261016.json'
        return json.loads(path.read_text(encoding='utf8'))[name]

    def test_location_with_colloquial_conjunction_keeps_both_fields(self):
        for conjunction in ('랑', '이랑', '하고', '와'):
            query = f'보건소 찾아가는 주소{conjunction} 평일 진료시간이 궁금합니다.'
            with self.subTest(query=query):
                self.assertIn('location', requested_goals(query))
                self.assertIn('hours', requested_goals(query))
                doc = self.document('health')
                result = structured_brief(query, doc, doc['content'], {'보건소'})
                self.assertIn('하신중앙로', result['answer'])
                self.assertIn('진료시간', result['answer'])

    def test_unrelated_words_do_not_become_location_fields(self):
        for query in ('공장 소음 신고 방법', '주소득자 기준', '위치료 상담'):
            self.assertFalse(asks_location(query), query)

    def test_numeric_deadline_confirmation_reads_source_value(self):
        doc = self.document('move')
        for claimed_days in (14, 30):
            query = f'전입신고는 전입한 뒤 {claimed_days}일 이내에 하는 게 맞죠?'
            self.assertEqual(answer_goal(query), 'schedule')
            result = structured_brief(query, doc, doc['content'], {'전입신고'})
            self.assertIn('14일', result['answer'])
            self.assertNotIn('30일', result['answer'])
            self.assertNotIn('제출처', result['answer'])

    def test_filing_deadline_cannot_use_processing_duration(self):
        query = '신청은 이사 후 20일 이내가 맞나요?'
        self.assertTrue(field_matches('schedule', '신청기한: 이사일부터 14일 이내 신청', query))
        self.assertFalse(field_matches('schedule', '처리기간: 10일 이내', query))

    def test_duration_incidental_to_documents_does_not_override_field(self):
        self.assertEqual(answer_goal('전입신고 14일 이내에 낼 준비서류 알려줘'), 'documents')
        self.assertEqual(answer_goal('전입신고 14일 이내 어디로 제출해요?'), 'method')


if __name__ == '__main__':
    unittest.main()
