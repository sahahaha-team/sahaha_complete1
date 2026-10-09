import threading
import unittest
from unittest.mock import Mock, patch

from chatbot.concise_answers import concise_source_answer
from chatbot.response_helpers import build_clarification, resolve_clarification_reply
from chatbot.conversation import ChatBot
from chatbot.verified_facts import parse_bed_fee, parse_adult_passport_fee, parse_disposal_schedule, answer_verified_table_question
from chatbot.answer_completion import model_answer_complete
from chatbot.faq_targets import match_official_page

PASSPORT = ("신규발급\n일반여권\n여권발급신청서 1부\n신분증(주민등록증, 운전면허증 등)\n"
    "여권용 컬러 사진 2매(최근 6개월 이내 촬영, 가로 3.5cm×세로 4.5cm, 정수리~턱까지의 길이가 3.2~3.6㎝)\n"
    "만18세 미만 미성년자의 여권 신청\n법정대리인\n긴급여권\n항공권 사본")


def original(body):
    return '공식 원문\n\n' + '\n'.join('> ' + line for line in body.splitlines())


class ConciseAnswerTests(unittest.TestCase):
    def brief(self, body):
        return concise_source_answer('재활용품 배출 방법', original(body), [{'metadata': {}}], {'재활용품'})

    def test_reported_recycling_sentence_keeps_wrapped_ending(self):
        result = self.brief('재활용품은 종량제봉투에 담지 않으며(일반쓰레기와 혼합배출시 과태료 부과),\n'
            '재활용품은 반드시 품목별로 분리하여 요일별로\n지정된 쓰레기만 배출하여야 합니다.')
        self.assertFalse(result['is_clarification'])
        self.assertTrue(result['answer'].endswith('합니다.'))
        self.assertIn('혼합배출시 과태료', result['answer'])
        self.assertIn('지정된 쓰레기', result['answer'])
        self.assertLess(len(result['answer']), 250)

    def test_incomplete_source_does_not_get_a_fabricated_ending(self):
        result = self.brief('재활용품은 반드시 품목별로 분리하여 요일별로')
        self.assertTrue(result['is_clarification'])
        self.assertTrue(result['answer'].endswith('?'))
        self.assertNotIn('배출하세요', result['answer'])

    def test_wrapped_exception_is_kept_whole(self):
        result = self.brief('재활용품은 분리하여 지정된 요일에 배출해야 합니다.\n다만 배출 품목이 다를 경우\n해당 재활용품을 배출할 수 없습니다.')
        self.assertIn('다만 배출 품목이 다를 경우 해당', result['answer'])
        self.assertTrue(result['answer'].endswith('없습니다.'))

    def test_cut_exception_requires_clarification(self):
        result = self.brief('재활용품은 분리하여 지정된 요일에 배출해야 합니다.\n다만 배출 품목이 다를 경우\n[…]')
        self.assertTrue(result['is_clarification'])

    def test_exception_is_not_selected_without_the_rule_it_qualifies(self):
        body = ('재활용품은 지정된 요일에 분리하여 배출해야 합니다.\n'
                '다만 재활용품 배출 방법에 예외가 있는 경우에는 별도 안내를 확인해야 합니다.')
        result = self.brief(body)
        self.assertIn('지정된 요일', result['answer'])
        self.assertIn('다만', result['answer'])

    def test_condition_is_not_detached_from_its_conclusion(self):
        result = self.brief('재활용품을 지정된 요일에 배출한 경우\n수거할 수 있습니다.')
        self.assertIn('배출한 경우 수거', result['answer'])

    def test_omitted_passage_edge_does_not_become_an_answer(self):
        for body in ('[…]\n재활용품은 지정된 요일에 배출해야 합니다.',
                     '재활용품은 지정된 요일에 배출해야 합니다.\n[…]'):
            self.assertTrue(self.brief(body)['is_clarification'])

    def test_wrapped_parentheses_are_balanced(self):
        result = self.brief('재활용품 배출 방법: 품목별로 분리(플라스틱,\n종이류 등)하여 배출합니다.')
        self.assertIn('(플라스틱, 종이류 등)', result['answer'])
        self.assertTrue(result['answer'].endswith('배출합니다.'))

    def test_table_header_is_not_joined_to_an_unfinished_claim(self):
        result = self.brief('재활용품은 요일별로\n배출요일\n월\n화\n종류\n플라스틱')
        self.assertTrue(result['is_clarification'])

    def test_long_complete_sentence_is_not_sliced(self):
        result = self.brief('재활용품 배출 방법: ' + '품목별 분리 조건을 확인하고 ' * 45 + '배출해야 합니다.')
        self.assertTrue(result['is_clarification'])
        self.assertLess(len(result['answer']), 160)

    def test_passport_summary_preserves_photo_conditions(self):
        result = concise_source_answer('성인 신규 여권 준비물', original(PASSPORT.split('만18세')[0]),
            [{'metadata': {'url': 'https://www.saha.go.kr/portal/contents.do?mId=0104020000'}}], {'여권', '신규'})
        self.assertFalse(result['is_clarification'])
        self.assertLess(len(result['answer']), 300)
        for condition in ('신분증', '2매', '6개월', '3.5cm', '4.5cm', '3.2~3.6'):
            self.assertIn(condition, result['answer'])
        self.assertTrue(result['answer_details'])

    def test_brief_must_keep_adjacent_exception(self):
        body = '신청 방법: 사하구 주민은 전화예약 후 방문상담을 신청합니다.\n다만 신청 대상에서 제외되는 경우에는 지원하지 않습니다.'
        result = concise_source_answer('방문상담 신청 방법', original(body), [{'metadata': {}}], {'방문상담'})
        self.assertIn('전화예약 후 방문상담', result['answer'])
        self.assertIn('제외', result['answer'])

    def test_table_cells_are_not_reassigned_to_a_summary(self):
        body = '여권 수수료\n유효기간\n58면\n52,000원\n만18세 이상\n26면\n49,000원'
        result = concise_source_answer('여권 수수료', original(body), [{'metadata': {}}], {'여권'})
        self.assertTrue(result['is_clarification'])
        self.assertNotIn('52,000원', result['answer'])

    def test_too_large_exception_requires_narrowing(self):
        body = '복지 신청 방법: 대상자는 주소지 관할 기관에 방문하여 신청서를 제출합니다.\n다만 ' + '조건과 예외를 확인해야 합니다. ' * 40
        result = concise_source_answer('복지 신청 방법', original(body), [{'metadata': {}}], {'복지'})
        self.assertTrue(result['is_clarification'])

    def test_renewal_summary_keeps_existing_passport_requirement(self):
        body = PASSPORT.split('만18세')[0] + '유효기간 남은 여권은 지참\n'
        result = concise_source_answer('성인 여권 재발급 준비물', original(body),
            [{'metadata': {'url': 'https://www.saha.go.kr/portal/contents.do?mId=0104020000'}}], {'여권', '재발급'})
        self.assertIn('기존 여권', result['answer'])

    def test_cost_table_keeps_total_and_included_parts(self):
        body = '수수료\n계\n수집·운반비\n처리비\n침대\n(매트리스, 서랍,\n부속장치 포함)\n일반침대 1인용\n14,000\n9,000\n5,000'
        answer = parse_bed_fee(body, '일반침대1인용수수료')
        self.assertIn('14,000원', answer)
        self.assertIn('매트리스', answer)
        self.assertIsNone(parse_bed_fee(body.replace('9,000', '8,000'), '일반침대1인용수수료'))

    def test_passport_fee_uses_requested_faces(self):
        body = '10년\n58면\n52,000원\n만18세 이상\n26면\n49,000원'
        self.assertIn('49,000원', parse_adult_passport_fee(body, '성인10년26면여권수수료'))
        self.assertIsNone(parse_adult_passport_fee(body, '성인여권수수료'))

    def test_short_method_label_keeps_visit_requirement(self):
        result = concise_source_answer('법률상담 신청 방법', original('방 법\n: 전화예약 후 방문상담'), [{'metadata': {}}], {'법률상담'})
        self.assertFalse(result['is_clarification'])
        self.assertIn('전화예약 후 방문상담', result['answer'])


class HouseholdDisposalAnswerTests(unittest.TestCase):
    RULE = ('일반쓰레기는 종량제봉투에 음식물쓰레기는 전용용기에 당일 저녁 7시부터 10시까지 '
            '대문앞(연립주택은 1층 출입구 밖)에 내어 놓아야 하며, 수거는 밤 10시부터 익일 오전 6시까지 합니다.')
    WARNING = ('재활용품은 종량제봉투에 담지 않으며(일반쓰레기와 혼합배출시 과태료 부과), '
               '재활용품은 반드시 품목별로 분리하여 요일별로 지정된 쓰레기만 배출하여야 합니다.')

    def test_household_method_uses_direct_rule_with_time_and_location_conditions(self):
        for query in ('일반쓰레기 배출 방법 알려줘', '음식물쓰레기 배출 방법 알려줘',
                      '쓰레기 배출 일반쓰레기', '쓰레기 배출 음식물', '사하구 일반쓰레기 어떻게 버려?',
                      '쓰레기 배출 방법 알려줘 일반쓰레기'):
            with self.subTest(query=query):
                source = original(self.RULE + '\n' + self.WARNING)
                result = concise_source_answer(query, source, [{'metadata': {}}], {'쓰레기', '일반쓰레기'})
                self.assertFalse(result['is_clarification'])
                self.assertIn(self.RULE, result['answer'])
                self.assertNotIn('혼합배출시 과태료', result['answer'])

    def test_recycling_warning_does_not_substitute_for_missing_household_rule(self):
        result = concise_source_answer('일반쓰레기 배출 방법 알려줘', original(self.WARNING),
                                       [{'metadata': {}}], {'쓰레기', '일반쓰레기'})
        self.assertTrue(result['is_clarification'])

    def test_recycling_method_uses_direct_rule_instead_of_background_definition(self):
        definition = '쓰레기 종량제는 재활용품을 최대한 분리 배출하도록 한 제도입니다.'
        query = '재활용품 분리배출 방법 알려줘'
        result = concise_source_answer(query, original(definition + '\n' + self.WARNING),
                                       [{'metadata': {}}], {'재활용품'})
        self.assertIn(self.WARNING, result['answer'])
        self.assertNotIn('제도입니다', result['answer'])
        self.assertEqual(match_official_page(query), 'https://www.saha.go.kr/portal/contents.do?mId=0405050101')
        for specific in ('사업장 재활용품 처리 방법', '재활용품 수거업체 전화번호', '음식물쓰레기 배출 시간', '일반쓰레기 과태료 얼마야'):
            self.assertNotEqual(match_official_page(specific), 'https://www.saha.go.kr/portal/contents.do?mId=0405050101')


class ClarificationFlowTests(unittest.TestCase):
    def make_bot(self):
        bot = object.__new__(ChatBot)
        bot.db = None
        bot._memory_history = {}
        bot._history_lock = threading.RLock()
        bot.retriever = Mock()
        return bot

    def test_broad_topics_prompt_one_focused_question(self):
        for query in ('복지 지원 알려줘', '여권 알려줘', '여권 준비물 알려줘', '대형폐기물 수수료 알려줘', '무인민원발급기 알려줘'):
            with self.subTest(query=query):
                result = build_clarification(query)
                self.assertIsNotNone(result)
                self.assertLess(len(result['answer']), 160)
                self.assertLessEqual(len(result['suggested_questions']), 3)

    def test_precise_question_is_answered_without_more_questions(self):
        for query in ('성인 신규 여권 준비물 알려줘', '보건증 발급 수수료', '대형폐기물 배출 방법', '공장 화재 신고 방법', '기초연금 신청 조건'):
            self.assertIsNone(build_clarification(query), query)

    def test_broad_waste_disposal_asks_type_before_searching(self):
        for query in ('쓰레기 배출', '쓰레기 배출 방법 알려줘', '생활쓰레기 어떻게 버려?', '사하구에서 폐기물 배출 안내'):
            with self.subTest(query=query):
                bot = self.make_bot()
                with patch('chatbot.contact_directory.contact_responder.respond', return_value=None):
                    result = bot.chat('waste', query)
                self.assertTrue(result['is_clarification'])
                self.assertIn('어떤 종류', result['answer'])
                self.assertEqual(result['sources'], [])
                self.assertEqual(result['evidence']['status'], 'clarification')
                self.assertFalse(result['degraded'])
                bot.retriever.search.assert_not_called()
                bot.retriever.search_official_url.assert_not_called()

    def test_precise_waste_questions_are_not_replaced_by_type_prompt(self):
        for query in ('쓰레기 배출 요일 알려줘', '쓰레기 배출 시간 알려줘', '수요일 분리수거 품목',
                      '일반쓰레기 배출 방법', '음식물쓰레기 배출 방법', '대형폐기물 배출 방법',
                      '쓰레기 불법투기 신고 방법', '사업장 폐기물 처리 방법', '폐기물 처리 통계'):
            with self.subTest(query=query):
                self.assertIsNone(build_clarification(query))

    def test_short_waste_type_keeps_pending_disposal_goal(self):
        clarification = build_clarification('쓰레기 배출')
        pending = {'query': '쓰레기 배출', **clarification}
        for reply in ('일반쓰레기', '음식물', '재활용품', '대형폐기물'):
            with self.subTest(reply=reply):
                resolved = resolve_clarification_reply(reply, pending)
                self.assertIn('쓰레기 배출', resolved)
                self.assertIn(reply, resolved)
                self.assertIsNone(build_clarification(resolved))
        self.assertEqual(resolve_clarification_reply('여권 준비물 알려줘', pending), '여권 준비물 알려줘')

    def test_typing_short_choices_keeps_question_context(self):
        bot = self.make_bot()
        with patch('chatbot.contact_directory.contact_responder.respond', return_value=None):
            first = bot.chat('flow', '여권 준비물 알려줘')
            self.assertIn('성인', first['answer'])
            second = bot.chat('flow', '성인이야')
            self.assertTrue(second['is_clarification'])
            self.assertIn('재발급', second['answer'])
        resolved = bot.contextual_message('flow', '처음이야')
        self.assertIn('여권', resolved)
        self.assertIn('성인', resolved)
        self.assertIn('처음', resolved)
        self.assertIsNone(build_clarification(resolved))
        bot.retriever.search.assert_not_called()
        self.assertEqual(first['sources'], [])
        self.assertEqual(second['sources'], [])

    def test_choice_button_is_complete_question_and_new_topic_is_not_attached(self):
        clarification = build_clarification('여권 준비물 알려줘')
        pending = {'query': '여권 준비물 알려줘', **clarification}
        button = clarification['suggested_questions'][0]
        self.assertEqual(resolve_clarification_reply(button, pending), button)
        self.assertEqual(resolve_clarification_reply('보건증 수수료 얼마야?', pending), '보건증 수수료 얼마야?')

    def test_reset_removes_pending_question(self):
        bot = self.make_bot()
        with patch('chatbot.contact_directory.contact_responder.respond', return_value=None):
            bot.chat('flow', '여권 준비물 알려줘')
        bot.clear_session('flow')
        self.assertEqual(bot.contextual_message('flow', '성인이야'), '성인이야')

    def test_sessions_do_not_share_pending_question(self):
        bot = self.make_bot()
        with patch('chatbot.contact_directory.contact_responder.respond', return_value=None):
            bot.chat('first', '여권 준비물 알려줘')
        self.assertEqual(bot.contextual_message('other', '성인이야'), '성인이야')

    def test_after_clarification_followup_does_not_lose_resolved_topic(self):
        bot = self.make_bot()
        bot._save_conversation_safe('flow', 'user', '처음이야', search_query='여권 준비물 성인 처음')
        bot._save_conversation_safe('flow', 'assistant', '신청서를 준비하세요.')
        query = bot.contextual_message('flow', '그럼 수수료는요?')
        self.assertIn('여권', query)
        self.assertNotIn('준비물', query)
        self.assertIsNotNone(build_clarification(query))

    def test_conversational_qualifiers_select_verified_passport_guide(self):
        url = match_official_page('여권 준비물 알려줘 성인이야 처음이야')
        self.assertIn('mId=0104020000', url)
        self.assertIsNone(match_official_page('유료 성인예방접종 알려줘'))


class ModelCompletionTests(unittest.TestCase):
    def test_token_limit_rejects_even_a_complete_visible_sentence(self):
        # The missing next sentence may contain an exception.
        self.assertFalse(model_answer_complete('방문하여 신청하세요.', {'done_reason': 'length'}))

    def test_incomplete_tail_and_unclosed_emphasis_are_rejected(self):
        for answer in ('방문하여 신청하세요. 다만 신청 대상인 경우', '**방문하여 신청하세요.', '신청하려면 먼저'):
            self.assertFalse(model_answer_complete(answer))

    def test_complete_short_bullets_and_decimals_are_accepted(self):
        answer = '- 사진은 3.5cm × 4.5cm 규격으로 준비하세요.\n- 신청서를 제출하세요.'
        self.assertTrue(model_answer_complete(answer, {'done_reason': 'stop'}))

    def test_complete_but_long_answer_is_not_exposed(self):
        self.assertFalse(model_answer_complete('방문하여 신청하세요. ' * 60))


class DisposalScheduleTests(unittest.TestCase):
    BODY = ('배출요일\n월\n화\n수\n목\n금\n토\n일\n쓰레기\n종류\n'
        '재활용품\n(플라스틱류(유색페트병\n포함),비닐류,\n요구르트병, 의류)\n'
        '일반쓰레기\n(가연성)\n음식물쓰레기\n'
        '재활용품(투명페트병,골판지류\n(박스 등), 기타종이류,\n종이팩류,유리병류, 스티로폼,\n'
        '캔‧고철류, 폐형광등,폐건전지등),\n일반쓰레기(불연성), 소형폐가전\n'
        '일반쓰레기 (가연성)\n음식물쓰레기\n배출\n금지\n배출\n금지\n'
        '일반쓰레기\n(가연성)\n음식물쓰레기\n이럴때는 쓰레기를 수거하지 않습니다.')

    def test_actual_question_returns_all_days_without_fragment(self):
        answer = parse_disposal_schedule(self.BODY, '요일별분리수거뭐해야하는데')
        for value in ('월요일', '수요일', '화·목·일요일', '금·토요일', '유색페트병', '투명페트병', '불연성', '배출 금지'):
            self.assertIn(value, answer)
        self.assertLess(len(answer), 350)
        self.assertTrue(answer.endswith('.'))

    def test_specific_day_is_not_answered_with_a_whole_week(self):
        answer = parse_disposal_schedule(self.BODY, '수요일분리수거')
        self.assertIn('투명페트병', answer)
        self.assertNotIn('유색페트병', answer)
        self.assertNotIn('금·토', answer)

    def test_changed_or_duplicate_columns_fail_closed(self):
        for body in (self.BODY.replace('월\n화', '화\n월'), self.BODY.replace('배출\n금지\n배출\n금지', '배출\n금지'), self.BODY * 2):
            self.assertIsNone(parse_disposal_schedule(body, '요일별분리수거'))

    def test_stale_schedule_is_not_presented_as_current(self):
        client = Mock()
        client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {'content': self.BODY, 'last_checked_at': '2000-01-01'}]
        result = answer_verified_table_question('요일별 분리수거 뭐해야하는데', client)
        self.assertFalse(result['verified'])
        self.assertEqual(result['sources'], [])
        self.assertIn('요일별 배출 품목', result['answer'])

    def test_other_disposal_services_and_time_queries_do_not_use_weekly_table(self):
        client = Mock()
        for query in ('대형폐기물 수거 요일', '분리수거 몇시에 해?', '요일별 분리수거 통계 건수'):
            self.assertIsNone(answer_verified_table_question(query, client))
        client.table.assert_not_called()


if __name__ == '__main__':
    unittest.main()
