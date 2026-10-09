"""Reported tax/support failures: source choice, intact conditions and followups."""
import unittest
from unittest.mock import patch

from chatbot.query_subject import normalize_query, substantive_keywords
from chatbot.response_helpers import build_clarification, resolve_clarification_reply
from chatbot.concise_answers import concise_source_answer
from chatbot.retriever import rank_service_sources
from crawler.site_sync import fetch_resource


def original(body):
    return '\n'.join('> ' + line for line in body.splitlines())


class TaxSupportTests(unittest.TestCase):
    def test_question_goal_does_not_become_an_unrelated_required_topic(self):
        self.assertEqual(substantive_keywords({'재산세', '날짜', '기준', '누구'}), {'재산세'})
        self.assertEqual(substantive_keywords({'기초연금', '조건', '대상', '수급'}), {'기초연금'})
        self.assertIn('기준중위소득', substantive_keywords({'기준중위소득', '조건'}))

    def test_senior_typo_and_broad_living_support_have_one_program_question(self):
        for query in ('어른신 생활비 지원 조건 알려줘', '어르신 생활비 지원 조건 알려줘', '노인 생활비 지원 알려줘'):
            result = build_clarification(query)
            self.assertEqual(result['answer'].count('?'), 1)
            self.assertIn('기초연금', result['answer'])
            self.assertIn('생계급여', result['answer'])
            self.assertNotIn('65세', result['answer'])
        self.assertEqual(normalize_query('어른신 생활비'), '어르신 생활비')

    def test_named_program_reply_replaces_broad_living_expense_wording(self):
        query = '어른신 생활비 지원 조건 알려줘'
        pending = {'query': query, **build_clarification(query)}
        for reply in ('기초연금', '기초연금이요', '생계급여', '생계급여요'):
            resolved = resolve_clarification_reply(reply, pending)
            self.assertNotIn('생활비', resolved)
            self.assertIsNone(build_clarification(resolved))
        button = pending['suggested_questions'][0]
        self.assertEqual(resolve_clarification_reply(button, pending), button)
        self.assertEqual(resolve_clarification_reply('재산세 누가 내나요?', pending), '재산세 누가 내나요?')
        self.assertEqual(resolve_clarification_reply('기초연금 말고 생계급여', pending), '기초연금 말고 생계급여')

    def test_tax_answer_keeps_date_and_actual_payer_from_the_source(self):
        body = ('재산세\n재산세는 매년 6월 1일 현재 토지,건축물,주택,선박,항공기를 보유한 자에 대하여 부과됩니다. '
                '7월에는 주택세액의 2분의 1을 부과합니다.')
        result = concise_source_answer('재산세는 어떤 날짜를 기준으로 누가 내나요?', original(body),
                                       [{'metadata': {}}], {'재산세'})
        self.assertFalse(result['is_clarification'])
        self.assertIn('6월 1일', result['answer'])
        self.assertIn('보유한 자', result['answer'])

    def test_eligibility_field_keeps_age_income_year_and_exclusion_together(self):
        section = ('만65세이상 노인으로 소득인정액이 선정기준액 이하인 자\n'
                   '선정기준액(2026년 1월 기준) : 단독가구 2,470,000원, 부부가구 3,952,000원\n'
                   '※ 신청불가 : 직역연금 대상자(퇴직금 수령자 포함)')
        meta = {'title': '기초연금안내 | 노인복지', 'section_heading': '신청대상', 'section_text': section}
        result = concise_source_answer('기초연금 신청 조건', original('신청대상\n' + section),
                                       [{'metadata': meta}], {'기초', '연금'})
        self.assertFalse(result['is_clarification'])
        for value in ('65세', '소득인정액', '2026년', '2,470,000', '3,952,000', '신청불가', '직역연금'):
            self.assertIn(value, result['answer'])

    def test_direct_service_and_requested_field_beat_incidental_mentions(self):
        rows = [
            {'id': 'other', 'bm25_score': 30, 'metadata': {'title': '저소득 영아 기저귀 지원', 'section_heading': '지원대상'}},
            {'id': 'apply', 'bm25_score': 20, 'content': '신청서류 및 선정기준액, 신청방법 안내',
             'metadata': {'title': '기초연금안내 | 노인복지', 'section_heading': '기초연금 신청'}},
            {'id': 'eligible', 'bm25_score': 10, 'metadata': {'title': '기초연금안내 | 노인복지', 'section_heading': '신청대상'}},
        ]
        ranked = rank_service_sources('기초연금 지원 조건', rows, {'기초', '연금'})
        self.assertEqual(ranked[0]['id'], 'eligible')

    def test_official_document_title_survives_a_generic_navigation_heading(self):
        html = ('<html><head><title>기초연금안내 | 노인복지 | 사하복지</title></head>'
                '<body><h2 class="title">노인복지</h2><main><h3>신청대상</h3><p>'
                + '공식 지원 조건과 제외 조건을 함께 안내합니다. ' * 4 + '</p></main></body></html>')
        url = 'https://www.saha.go.kr/portal/contents.do?mId=0502030200'
        with patch('crawler.site_sync.get_public', return_value=(200, {'Content-Type': 'text/html'}, html.encode(), url)):
            result = fetch_resource({'url': url, 'kind': 'page', 'title': None})
        self.assertTrue(result['title'].startswith('기초연금안내'))
        self.assertEqual(result['status'], 'fetched')

    def test_payment_termination_does_not_outrank_eligibility_criteria(self):
        rows = [
            {'id': 'stop', 'bm25_score': 30, 'content': '조건불이행 처리',
             'metadata': {'title': '자활사업', 'section_heading': '조건불이행 시의 생계급여 중지결정'}},
            {'id': 'criteria', 'bm25_score': 10, 'content': '[2026년 생계급여 최저보장수준 및 선정기준]',
             'metadata': {'title': '수급자지원 | 기초생활보장', 'section_heading': '생계급여 : 일상생활에 필요한 금품 지급'}},
        ]
        self.assertEqual(rank_service_sources('생계급여 지원 대상 조건', rows, {'생계', '급여'})[0]['id'], 'criteria')
        from chatbot.question_intent import requested_field_score
        self.assertEqual(requested_field_score('생계급여 중지 조건', '조건불이행 시의 생계급여 중지결정'), 1)

    def test_structured_source_section_omits_satisfaction_and_footer(self):
        from chatbot.source_answers import strip_page_chrome
        text = '지원대상\n소득 기준을 충족하는 가구\n이 페이지에서 제공하는 정보에 만족하십니까?\n담당자\n부서'
        self.assertEqual(strip_page_chrome(text), '지원대상\n소득 기준을 충족하는 가구')


if __name__ == '__main__':
    unittest.main()
