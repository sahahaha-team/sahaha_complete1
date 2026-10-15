"""Regressions from real consultations; facts remain source-derived."""
import unittest
import json
from pathlib import Path
from unittest.mock import Mock

from chatbot.answer_goal import answer_goal, quantity_unit
from chatbot.query_subject import interpret_query, normalize_query
from chatbot.response_helpers import build_clarification
from chatbot.passport_documents import parse_passport_documents
from chatbot.official_content import official_html_text
from chatbot.structured_answers import structured_brief, field_matches
from chatbot.evidence_decision import document_decision
from chatbot.grounded_planner import answer_with_grounded_model
from chatbot.concise_answers import concise_source_answer
from tests.test_passport_documents import HTML


class QueryConsistencyTests(unittest.TestCase):
    def test_renewal_variants_keep_the_complete_requirement_set(self):
        body = official_html_text(HTML)
        queries = ('성인 여권 재발급 준비물', '성인 여권 재 발급 준비물 알려줘',
                   '어른 여권 다시 발급받으려면 뭘 가져가야 해?',
                   '성인 여권 신규 발급이 아니라 재발급 준비물')
        answers = [parse_passport_documents(q, body) for q in queries]
        self.assertTrue(all(a == answers[0] for a in answers))
        for query in queries:
            self.assertIsNone(build_clarification(query))
        self.assertIn('기존 여권', answers[0])
        self.assertIn('추가 서류', answers[0])

    def test_corrections_do_not_erase_negated_facts_or_change_age(self):
        for query in ('성인 신규 여권 서류', '17살 본인 여권 서류',
                      '여권 재발급이 아니에요', '신분증 없이 여권 신청',
                      '부모가 성인 대신 여권 신청', '부산진구 보건소 주소'):
            self.assertEqual(interpret_query(query), query)
        self.assertEqual(interpret_query('주민등록증 발급 말고 분실 신고 방법'),
                         '주민등록증 분실 신고 방법')
        self.assertIn('만 18세 미만', build_clarification('고등학생 여권 준비물')['answer'])
        self.assertIsNone(parse_passport_documents('부모가 성인 대신 여권 신청 서류', official_html_text(HTML)))

    def test_clear_method_does_not_require_an_extra_question(self):
        for query in ('대형 폐기물 어떻게 버려요?', '대형폐기물 버리는 절차',
                      '대형페기물 배출 방법 알려줘'):
            self.assertEqual(answer_goal(query), 'method')
            self.assertIsNone(build_clarification(query))
        self.assertIsNotNone(build_clarification('대형폐기물 수수료'))

    def test_closed_typo_correction_and_spacing_preserve_service(self):
        self.assertIn('처음 발급', build_clarification('주민등룍증 발급 절차 알려줘')['answer'])
        self.assertIn('주민등록증', normalize_query('주민 등록증 발급'))
        self.assertEqual(normalize_query('외국인등록증과 시민증'), '외국인등록증과 시민증')

    def test_count_limit_is_not_the_application_method_or_purchase_duration(self):
        query = '희망 도서 월별 신청 한도 알려줘'
        body = '## 희망도서 신청\n신청방법: 홈페이지에서 신청\n신청권수: 1인 월 2권, 연 15권\n처리기간: 구입까지 1개월'
        doc = {'content': body, 'metadata': {'title': '희망도서 신청', 'url': 'https://www.saha.go.kr/portal/contents.do?mId=test'}}
        answer = structured_brief(interpret_query(query), doc, body, {'희망도서'})
        self.assertIn('월 2권', answer['answer'])
        self.assertNotIn('1개월', answer['answer'])
        self.assertFalse(field_matches('schedule', '처리기간: 1개월', query))
        self.assertEqual(answer_goal('기부금 연간 한도 얼마'), 'cost')
        self.assertIsNone(quantity_unit('지원금 신청 금액 한도'))


class SourceOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((Path(__file__).parent / 'fixtures/accuracy_sources_20261015.json').read_text(encoding='utf-8'))

    def document(self, index):
        row = self.rows[index]
        body = official_html_text(row['html'])
        return {'content': body, 'metadata': {'title': row['title'], 'url': row['url'], 'source_type': 'crawled_page'}}

    def test_general_institution_address_cannot_be_a_vaccination_venue(self):
        q = '보건소 주소는?'
        wrong = {'content': '## 어르신 폐렴구균 예방접종\n접종장소: 보건소 접종 미운영, 전국 위탁의료기관',
                 'metadata': {'title': '어르신 폐렴구균 예방접종', 'url': 'https://www.saha.go.kr/health/contents.do?mId=wrong'}}
        self.assertFalse(document_decision(q, wrong, {'보건소'})['relevant'])
        doc = self.document(0)
        self.assertEqual(document_decision(q, doc, {'보건소'})['decision'], 'supported')
        llm = Mock()
        answer = answer_with_grounded_model(q, [doc], None, {'보건소'}, llm)
        self.assertIn('하신중앙로 185', answer['answer'])
        llm.model_copy.assert_not_called()

    def test_specific_benefit_retains_its_own_extra_child_condition(self):
        q = '둘째 아이만 있어도 광안대교 통행료가 무료인가요?'
        doc = self.document(1)
        keys = {'광안대교', '통행료'}
        answer = structured_brief(q, doc, doc['content'], keys)
        self.assertIn('3자녀 이상', answer['answer'])
        self.assertIn('통행료 면제', answer['answer'])
        self.assertNotIn('손세정제', answer['answer'])
        llm = Mock()
        planned = answer_with_grounded_model(q, [doc], None, keys, llm)
        self.assertIn('3자녀 이상', planned['answer'])
        llm.model_copy.assert_not_called()
        original = '\n'.join('> ' + line for line in doc['content'].splitlines())
        fallback = concise_source_answer(q, original, [doc], keys)
        self.assertIn('3자녀 이상', fallback['answer'])

    def test_compound_request_uses_actual_exclusions_not_a_lookup_instruction(self):
        q = '희망도서는 어디서 신청하고 어떤 책은 제외돼요?'
        doc = self.document(2)
        answer = structured_brief(q, doc, doc['content'], {'희망도서'})
        self.assertIn('로그인', answer['answer'])
        self.assertIn('선정제외기준:', answer['answer'])
        self.assertIn('일부', answer['answer'])
        self.assertTrue(answer['degraded'])
        self.assertFalse(field_matches('conditions', '신청방법: 선정 제외도서 확인', q))

    def test_nested_exclusions_keep_the_label_and_do_not_absorb_other_cases(self):
        doc = self.document(3)
        self.assertIn('신청제외대상: 신청과 관련된 수사·소송·행정심판', doc['content'])
        q = '이미 소송 중인 건도 사전컨설팅감사를 받을 수 있나요?'
        answer = structured_brief(q, doc, doc['content'], {'사전컨설팅감사'})
        self.assertIn('신청제외대상:', answer['answer'])
        self.assertIn('소송', answer['answer'])

    def test_reply_duration_keeps_the_delay_exception(self):
        doc = self.document(3)
        q = '사전컨설팅감사를 신청하면 답변은 며칠 안에 오나요?'
        answer = structured_brief(q, doc, doc['content'], {'사전컨설팅감사'})
        self.assertIn('30일 이내', answer['answer'])
        self.assertIn('지연될 수 있음', answer['answer'])
