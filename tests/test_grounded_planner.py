import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from chatbot.grounded_planner import render_plan, answer_with_grounded_model, prepare_evidence, plan_context, eligible_ids
from chatbot.concise_answers import concise_source_answer
from chatbot.response_helpers import resolve_clarification_reply


def packet(units, title='소방 안전교육'):
    return {'units': units, 'body': '\n'.join(units), 'document': {
        'content': '\n'.join(units), 'metadata': {'title': title,
            'url': 'https://www.saha.go.kr/portal/contents.do?mId=test', 'source_type': 'crawled_page'}}}


class GroundedPlannerTests(unittest.TestCase):
    def test_scoped_course_asks_about_audience_before_presenting_venue(self):
        p = packet(['관리주체 소방 안전교육', '장 소 : 사하구청(예정)',
                    '대 상 : 공동주택 경비책임자, 시설물안전관리책임자'])
        r = render_plan('소방 안전 교육 어디서 들어', {'mode':'answer', 'source':0, 'units':[1]}, [p], {'소방','안전','교육'})
        self.assertTrue(r['is_clarification'])
        self.assertIn('경비책임자', r['answer'])
        self.assertNotIn('사하구청', r['answer'])

    def test_confirmed_audience_does_not_turn_planned_venue_into_confirmed_venue(self):
        p = packet(['관리주체 소방 안전교육', '장 소 : 사하구청(예정)', '대 상 : 공동주택 경비책임자'])
        r = render_plan('공동주택 소방 안전 교육 어디서 들어', {'mode':'answer','source':0,'units':[1]}, [p], {'소방','안전','교육'})
        self.assertFalse(r['is_clarification'])
        self.assertIn('확정 정보는 확인되지', r['answer'])
        self.assertIn('예정', r['answer'])
        self.assertIn('경비책임자', r['answer'])

    def test_venue_from_next_course_is_rejected_even_on_same_page(self):
        p = packet(['관리주체 소방 및 방범교육', '교육내용 : 소방에 관한 안전교육',
            '장소 : 사하구청(예정)', '대상 : 공동주택 경비책임자',
            '입주자대표회의 운영 및 윤리교육', '장소 : 다른 교육장', '대상 : 동별대표자'], '공동주택 관리 안내')
        self.assertIsNone(render_plan('소방 안전 교육 어디서 들어',
            {'mode':'answer','source':0,'units':[5]}, [p], {'소방','안전','교육'}))

    def test_exception_is_kept_without_model_having_to_select_it(self):
        p = packet(['정화조 청소는 연 1회 실시해야 합니다.', '※ 특수 시설은 별도 기준을 확인해야 합니다.'], '정화조 청소')
        r = render_plan('정화조 청소 주기', {'mode':'answer','source':0,'units':[0]}, [p], {'정화조','청소'})
        self.assertIn('연 1회', r['answer'])
        self.assertIn('별도 기준', r['answer'])

    def test_invented_text_ids_and_incomplete_units_cannot_enter_answer(self):
        p = packet(['보건소 운영시간 : 09:00~18:00', '오후에는 접수를 하여'], '보건소')
        for ids in ([99], [-1], ['새로운 장소'], [True], [1]):
            with self.subTest(ids=ids):
                self.assertIsNone(render_plan('보건소 여는시간', {'mode':'answer','source':0,'units':ids}, [p], {'보건소'}))

    def test_answer_requires_the_requested_field(self):
        p = packet(['보건소 주소 : 낙동대로 100'], '보건소')
        self.assertIsNone(render_plan('보건소 여는시간', {'mode':'answer','source':0,'units':[0]}, [p], {'보건소'}))

    def test_model_failure_uses_fallback_contract(self):
        p = packet(['정화조 청소는 연 1회 실시해야 합니다.'], '정화조 청소')
        llm = Mock()
        llm.model_copy.return_value.invoke.side_effect = RuntimeError('model unavailable')
        self.assertIsNone(answer_with_grounded_model('정화조 청소 주기', [p['document']], None, {'정화조','청소'}, llm))

    def test_normal_question_actually_calls_model_and_uses_selected_fact(self):
        p = packet(['정화조 청소는 연 1회 실시해야 합니다.'], '정화조 청소')
        llm = Mock()
        llm.model_copy.return_value.invoke.return_value = SimpleNamespace(
            content=json.dumps({'mode':'answer','source':0,'units':[0]}), response_metadata={'done_reason':'stop'})
        r = answer_with_grounded_model('정화조 청소 주기', [p['document']], None, {'정화조','청소'}, llm)
        llm.model_copy.return_value.invoke.assert_called_once()
        self.assertIn('연 1회', r['answer'])

    def test_source_only_fallback_keeps_course_scope(self):
        p = packet(['관리주체 소방 안전교육', '장 소 : 사하구청(예정)',
                    '대 상 : 공동주택 경비책임자, 시설물안전관리책임자'])
        quote = '\n'.join('> ' + unit for unit in p['units'])
        r = concise_source_answer('소방 안전 교육 어디서 들어', quote, [p['document']], {'소방','안전','교육'})
        self.assertTrue(r['is_clarification'])
        self.assertIn('경비책임자', r['answer'])
        self.assertNotIn('사하구청', r['answer'])

    def test_portal_printing_conditions_are_not_candidates_for_move_report(self):
        p = packet(['전입신고 등을 인터넷으로 신청',
                    '이용방법 : 회원가입 또는 비회원으로 실명인증 후 이용할 수 있습니다.',
                    '민원서류 발급을 위하여 출력 가능한 프린터가 준비 되어야 합니다.'], '정부24')
        self.assertEqual(eligible_ids('전입신고 어떻게 해?', p, {'전입신고'}), {0})

    def test_frequency_question_cannot_answer_with_fee_calculator(self):
        p = packet(['정화조는 연 1회 청소해야 합니다.',
                    '정화조 용량을 입력하면 수수료가 자동 계산됩니다.'], '정화조 청소')
        self.assertEqual(eligible_ids('정화조 청소 얼마나 자주 해야 해?', p, {'정화조','청소'}), {0})
        self.assertIsNone(render_plan('정화조 청소 얼마나 자주 해야 해?',
            {'mode':'answer','source':0,'units':[1]}, [p], {'정화조','청소'}))

    def test_general_resident_condition_does_not_erase_general_waste_topic(self):
        from chatbot.query_subject import query_keywords
        self.assertEqual(query_keywords('일반 주민 소방 안전교육', ['일반','주민','소방','안전','교육']), {'소방','안전','교육'})
        self.assertIn('일반', query_keywords('일반 쓰레기 배출요일', ['일반','쓰레기','배출']))

    def test_model_context_budget_does_not_drop_hidden_exception_from_answer(self):
        p = packet(['정화조 청소는 연 1회 실시해야 합니다.',
                    '※ 별도 기준이 있는 시설은 담당 부서의 기준을 확인해야 합니다.'], '정화조 청소')
        p['visible_ids'] = [0]
        r = render_plan('정화조 청소 주기', {'mode':'answer','source':0,'units':[0]}, [p], {'정화조','청소'})
        self.assertIn('별도 기준', r['answer'])
        self.assertIsNone(render_plan('정화조 청소 주기', {'mode':'answer','source':0,'units':[1]}, [p], {'정화조','청소'}))

    def test_course_yes_no_replies_keep_confirmed_scope_without_repeating_question(self):
        p = packet(['관리주체 소방 안전교육', '장 소 : 사하구청(예정)', '대 상 : 공동주택 경비책임자'])
        q = '소방 안전 교육 어디서 들어'
        r = render_plan(q, {'mode':'answer','source':0,'units':[1]}, [p], {'소방','안전','교육'})
        pending = {**r, 'query':q}
        yes = resolve_clarification_reply('네', pending)
        self.assertIn('경비책임자', yes)
        r_yes = render_plan(yes, {'mode':'answer','source':0,'units':[1]}, [p], {'소방','안전','교육'})
        self.assertFalse(r_yes['is_clarification'])
        self.assertIn('확정 정보는 확인되지', r_yes['answer'])
        no = resolve_clarification_reply('아니요', pending)
        self.assertIn('일반 주민', no)
        r_no = render_plan(no, {'mode':'answer','source':0,'units':[1]}, [p], {'소방','안전','교육'})
        self.assertFalse(r_no['is_clarification'])
        self.assertIn('이 자료에서 확인되지', r_no['answer'])
        self.assertNotIn('사하구청', r_no['answer'])


if __name__ == '__main__':
    unittest.main()
