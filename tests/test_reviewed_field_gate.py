import unittest
from unittest.mock import Mock, patch

from chatbot.grounded_planner import answer_with_grounded_model
from chatbot.source_warnings import reviewed_field_answer
from chatbot.request_metrics import request_metrics


def clinic(body=None):
    body = body or ('## 물리치료실\n대상: 1차 진료 후 의사 처방에 의하여 물리치료가 필요한 분\n'
                    'Step 4. 치료 1층 물리치료실\n진료장소 : 3층 물리치료실')
    return {'content': body, '_raw_page': {'content': body}, 'metadata': {
        'url': 'https://www.saha.go.kr/health/contents.do?mId=0201020000',
        'title': '물리치료실', 'source_type': 'crawled_page'}}


class ReviewedFieldGateTests(unittest.TestCase):
    def test_quarantined_field_checks_eligibility_without_extracting_removed_field(self):
        with patch('chatbot.evidence_decision._coverage') as coverage:
            result = reviewed_field_answer('물리치료실 위치', [clinic()], None, {'물리치료'})
        coverage.assert_not_called()
        self.assertEqual(result['degraded_reason'], 'source_conflict')

    def test_eligibility_only_never_marks_a_source_as_supported(self):
        from chatbot.evidence_decision import document_decision
        result = document_decision('물리치료실 대상', clinic(), {'물리치료'}, check_fields=False)
        self.assertTrue(result['relevant'])
        self.assertEqual(result['decision'], 'needs_evidence')
        self.assertEqual(result['matched_fields'], [])

    def test_preflight_without_a_reviewed_url_does_not_fetch_any_original(self):
        document = {'content': '다른 업무 안내', 'metadata': {
            'title': '다른 업무', 'url': 'https://www.saha.go.kr/portal/other'}}
        client = Mock()
        self.assertIsNone(reviewed_field_answer('위치', [document], client, {'다른업무'}))
        client.table.assert_not_called()

    def test_conflict_is_explained_with_source_without_calling_model(self):
        llm = Mock()
        with request_metrics() as metrics:
            result = answer_with_grounded_model('물리치료실 위치 어디인가요?', [clinic()], None, {'물리치료'}, llm)
        self.assertEqual(result['answer_method'], 'reviewed_source_field')
        self.assertEqual(result['evidence_status'], 'conflicting')
        self.assertIn('다르게 표시', result['answer'])
        self.assertEqual(result['documents'][0]['metadata']['url'], clinic()['metadata']['url'])
        self.assertEqual(metrics.model_calls, [])
        llm.model_copy.assert_not_called()

    def test_unblocked_field_and_changed_source_are_not_refused(self):
        for query, doc in [('물리치료실 대상', clinic()),
                           ('물리치료실 위치', clinic('## 물리치료실\n진료장소 : 3층 물리치료실'))]:
            self.assertIsNone(reviewed_field_answer(query, [doc], None, {'물리치료'}))

    def test_mixed_request_continues_to_partial_answer_and_other_service_is_not_warning(self):
        self.assertIsNone(reviewed_field_answer('물리치료실 위치와 대상', [clinic()], None, {'물리치료'}))
        self.assertIsNone(reviewed_field_answer('금연클리닉 위치', [clinic()], None, {'금연클리닉'}))

    def test_scope_only_is_not_a_medication_dose_candidate(self):
        body = '## 금연클리닉\n대상: 금연을 원하는 지역주민\n내용: 금연상담 및 금연보조제 제공'
        doc = {'content': body, '_raw_page': {'content': body}, 'metadata': {
            'title': '금연클리닉', 'url': 'https://www.saha.go.kr/health/test', 'source_type': 'crawled_page'}}
        llm = Mock()
        answer_with_grounded_model('금연약 복용량 하루 몇 정', [doc], None, {'금연'}, llm)
        llm.model_copy.assert_not_called()
