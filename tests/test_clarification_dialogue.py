"""Scope confirmations must preserve the service and the requested field."""
from collections import OrderedDict
import threading
import time
import unittest

from chatbot.answer_goal import answer_goal, requested_goals
from chatbot.concise_answers import course_scope_result, concise_source_answer
from chatbot.conversation import ChatBot
from chatbot.response_helpers import build_clarification, build_contextual_search_query, resolve_clarification_reply
from chatbot.structured_answers import structured_brief


QUERY = '소방 교육 하는방법 알려줘'
AUDIENCE = '의무관리대상 공동주택단지 경비책임자, 시설물안전관리책임자'
BODY = ('## 공동주택 관리 안내\n### 놀이시설 안전교육\n신청방법: 다른 기관 사이트 신청\n'
        '### 관리주체 소방 및 방범교육\n대 상 : ' + AUDIENCE + '\n장 소 : 사하구청(예정)\n일 시 : 상반기 중 예정')
DOC = {'content': BODY, 'metadata': {'title': '공동주택 관리 안내',
       'url': 'https://www.saha.go.kr/portal/contents.do?mId=test'}}


def source_reply(query):
    return structured_brief(query, DOC, BODY, {'소방'}) or concise_source_answer(
        query, '\n'.join('> ' + line for line in BODY.splitlines()), [DOC], {'소방'})


class ClarificationDialogueTests(unittest.TestCase):
    def setUp(self):
        self.pending = {**course_scope_result(QUERY, '대상: ' + AUDIENCE), 'query': QUERY}

    def test_natural_confirmations_retain_field_and_do_not_repeat(self):
        for reply in ('어 맞아', '네 맞아요', '응, 맞아!', '그 교육 맞아요', '맞으니까 참여방법 알려줘'):
            with self.subTest(reply=reply):
                query = resolve_clarification_reply(reply, self.pending)
                self.assertIn('소방', query)
                self.assertIn(AUDIENCE, query)
                self.assertEqual(answer_goal(query), 'method')
                self.assertEqual(requested_goals(query), ('method',))
                result = source_reply(query)
                self.assertFalse(result['is_clarification'])
                self.assertTrue(result['degraded'])
                self.assertIn('이용 방법', result['answer'])
                self.assertNotIn('다른 기관 사이트 신청', result['answer'])

    def test_confirmation_plus_new_field_does_not_keep_old_field(self):
        query = resolve_clarification_reply('네, 비용 알려줘', self.pending)
        self.assertIn(AUDIENCE, query)
        # A new explicit field must not be shadowed by the original method.
        self.assertEqual(answer_goal(query), 'cost')

    def test_negative_confirmation_does_not_establish_specialized_audience(self):
        for reply in ('아니요', '아냐', '안 맞아요', '맞지 않아', '아니요 일반 주민이에요'):
            query = resolve_clarification_reply(reply, self.pending)
            self.assertIn('일반 주민', query, reply)
            self.assertNotIn(AUDIENCE, query)
            result = structured_brief(query, DOC, BODY, {'소방'})
            self.assertFalse(result['is_clarification'])
            self.assertIn('일반 주민', result['answer'])
            self.assertNotIn('다른 기관', result['answer'])

    def test_uncertain_reply_never_confirms_audience(self):
        for reply in ('잘 모르겠어', '맞는지 모르겠어', '해당하는지 모르겠어요'):
            query = resolve_clarification_reply(reply, self.pending)
            self.assertEqual(query, QUERY)
            self.assertTrue(structured_brief(query, DOC, BODY, {'소방'})['is_clarification'])

    def test_new_named_service_overrides_acknowledgement(self):
        for reply in ('네 여권 준비물 알려줘', '아니요 마을세무사 상담 방법 알려줘', '어 맞아 보건소 위치 알려줘'):
            self.assertEqual(resolve_clarification_reply(reply, self.pending), reply)

    def test_choices_are_complete_questions_and_use_same_confirmation_state(self):
        choices = self.pending['suggested_questions']
        self.assertEqual(len(choices), 2)
        for choice in choices:
            self.assertIn('소방', choice)
            query = resolve_clarification_reply(choice, self.pending)
            self.assertEqual(answer_goal(query), 'method')
            self.assertFalse(source_reply(query)['is_clarification'])

    def test_third_turn_and_elided_field_keep_confirmed_profile(self):
        query = resolve_clarification_reply('어 맞아', self.pending)
        history = [{'role': 'user', 'content': '어 맞아', 'search_query': query}]
        for reply in ('맞으니까 참여방법 알려줘', '신청은 어떻게 해요?', '위치 알려줘', '그럼 일정은요?'):
            merged = build_contextual_search_query(reply, history)
            self.assertIn(AUDIENCE, merged)
            self.assertIn('소방', merged)
            self.assertIn('교육', merged)
            if '일정' in reply:
                self.assertEqual(answer_goal(merged), 'schedule')
                self.assertNotIn('참여방법', merged)
            self.assertFalse(source_reply(merged)['is_clarification'])
        self.assertEqual(build_contextual_search_query('성인 신규 여권 준비물 알려줘', history), '성인 신규 여권 준비물 알려줘')

    def test_other_course_uses_its_own_audience_and_preserves_numbers(self):
        pending = {**course_scope_result('안전교육 신청 방법', '대상: 18세 이상 근로자'), 'query': '안전교육 신청 방법'}
        query = resolve_clarification_reply('네 맞아요', pending)
        self.assertIn('18세 이상 근로자', query)
        self.assertEqual(requested_goals(query), ('method',))

    def test_session_isolation_and_expiry_do_not_transfer_scope(self):
        bot = ChatBot.__new__(ChatBot)
        bot.db = None
        bot._history_lock = threading.RLock()
        bot._memory_history = {}
        bot._pending_clarifications = OrderedDict()
        bot._clarification_result('a', QUERY, QUERY, self.pending)
        self.assertIn(AUDIENCE, bot.contextual_message('a', '어 맞아'))
        self.assertEqual(bot.contextual_message('b', '어 맞아'), '어 맞아')
        bot._pending_clarifications['a']['created_at'] = time.monotonic() - 1801
        self.assertNotIn(AUDIENCE, bot.contextual_message('a', '어 맞아'))

    def test_non_yes_no_clarification_does_not_invent_a_selection(self):
        pending = {'query': '여권 준비물 알려줘', 'reply_terms': ['성인','미성년'], 'suggested_questions': []}
        self.assertNotIn('성인', resolve_clarification_reply('네 맞아요', pending))

    def test_confirmation_field_without_context_asks_for_service(self):
        query = build_contextual_search_query('맞으니까 참여방법 알려줘', [])
        self.assertTrue(build_clarification(query)['suggested_questions'] == [])
        self.assertIn('어떤 시설이나 업무', build_clarification(query)['answer'])
        query = build_contextual_search_query('네 비용 알려줘', [{'role':'user','content':'성인 신규 여권 준비물 알려줘'}])
        self.assertIn('여권', query)
        self.assertEqual(answer_goal(query), 'cost')

    def test_confirmed_audience_rejects_another_program_sharing_the_topic(self):
        from chatbot.evidence import is_service_source
        query = resolve_clarification_reply('네 맞아요', self.pending)
        query = build_contextual_search_query('그럼 일정은요?', [{'role':'user','content':'네 맞아요','search_query':query}])
        child = {'content':'## 소방안전교육센터\n이용대상: 4세 이상 13세 이하 어린이\n체험시간: 화~금 09:30~10:30',
                 'metadata':{'title':'이용안내','url':'https://www.saha.go.kr/reserve/contents.do?mId=1207000000'}}
        self.assertFalse(is_service_source(query, child, {'소방'}))
        self.assertTrue(is_service_source(query, DOC, {'소방'}))
        # An explicit new topic must still be able to select its own audience.
        self.assertTrue(is_service_source('어린이 소방교육 일정', child, {'소방'}))


if __name__ == '__main__':
    unittest.main()
