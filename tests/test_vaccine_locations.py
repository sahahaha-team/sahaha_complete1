import threading
import unittest
from unittest.mock import Mock, patch

from chatbot.concise_answers import concise_source_answer
from chatbot.conversation import ChatBot
from chatbot.faq_targets import match_official_page
from chatbot.question_intent import asks_location, has_location, location_source_units
from chatbot.query_subject import fallback_keywords
from chatbot.response_helpers import build_clarification, resolve_clarification_reply, build_contextual_search_query
from chatbot.source_answers import build_source_answer, focused_section
from chatbot.vaccination import ADULT_VACCINE_URL, vaccine_kind

# Current official headings/fields, not a generated answer or clinical advice.
BODY = '''유료 및 성인 예방접종 안내
유료 및 성인예방접종 장소, 내용, 문의 안내
장소
사하구보건소 1층 예방접종실
접수시간
오전: 09:00 ~ 11:30
오후: 13:00 ~ 17:30
종류
B형 간염
A형 간염
65세 이상 어르신 폐렴구균 예방접종
대상 : 65세 이상인 자 (1961.12.31.이전 출생자)
접종장소 : 보건소 접종 미운영, 전국 지정 위탁의료기관에서 주소지 무관 접종 가능
시행백신 : 다당질 백신 프로디악스 23가(PPSV23)
과거 65세 이상 연령에서 폐렴구균 23가 다당질백신(PPSV23)을 접종(의료기관에서 유료로 접종했거나, 보건소에서 무료로 접종했을 때)한 경우 접종 불필요
인플루엔자 예방접종
대상 : 12세 이하 어린이, 65세 이상 어르신 및 부산시 지자체 대상자(생계·의료급여 수급권자, 심한장애인, 국가유공자 본인)
시기 : 매년 10월 중 시작(절기 사업으로 사업 종료 시 접종 안됨)
비용 : 무료 (※현재 보건소에서는 직접 주사 안됨)
접종장소 : 전국 지정 위탁의료기관 (지자체 대상자는 부산시 지정 위탁의료기관만 가능)
※ 지정의료기관은 매년 독감접종 시작전 공고 예정
해외여행자 예방접종
황열 및 콜레라 : 영도병원(문의 1899-0061)'''
HISTORY = BODY.split('과거', 1)[1].split('\n', 1)[0]


def summary(query, body=BODY):
    section = focused_section(query, ADULT_VACCINE_URL, body)
    text = section if section is not None else body
    return concise_source_answer(query, '\n'.join('> ' + line for line in text.splitlines()),
        [{'metadata': {'url': ADULT_VACCINE_URL}}], fallback_keywords(query))


class VaccinePlaceTests(unittest.TestCase):
    def test_original_unspecified_vaccine_prompts_one_short_question_without_search(self):
        bot = object.__new__(ChatBot)
        bot.db = None
        bot._memory_history = {}
        bot._history_lock = threading.RLock()
        bot.retriever = Mock()
        with patch('chatbot.contact_directory.contact_responder.respond', return_value=None):
            result = bot.chat('vaccine', '백신 접종 하는곳 알려줘')
        self.assertTrue(result['is_clarification'])
        self.assertIn('어떤 백신', result['answer'])
        self.assertNotIn('접종 불필요', result['answer'])
        self.assertLess(len(result['answer']), 140)
        self.assertEqual(result['sources'], [])
        bot.retriever.search.assert_not_called()
        bot.retriever.search_official_url.assert_not_called()

    def test_colloquial_generic_location_questions_also_ask_the_type(self):
        for query in ('예방접종 어디서 해?', '백신 맞는 곳 알려줘', '백신 접종장소 알려줘'):
            self.assertIsNotNone(build_clarification(query), query)

    def test_short_type_reply_keeps_place_goal_and_new_topic_stays_separate(self):
        pending = {'query': '백신 접종 하는곳 알려줘', **build_clarification('백신 접종 하는곳 알려줘')}
        resolved = resolve_clarification_reply('독감', pending)
        self.assertIn('하는곳', resolved)
        self.assertEqual(vaccine_kind(resolved), '인플루엔자')
        self.assertIsNone(build_clarification(resolved))
        self.assertEqual(resolve_clarification_reply('여권 발급 준비물', pending), '여권 발급 준비물')
        self.assertEqual(resolve_clarification_reply('B형간염 검사 비용 알려줘', pending), 'B형간염 검사 비용 알려줘')

    def test_followup_cost_keeps_vaccine_type_but_replaces_previous_place_goal(self):
        query = build_contextual_search_query('그럼 비용은요?',
            [{'role': 'user', 'content': '독감 접종 장소 알려줘'}])
        self.assertIn('독감', query)
        self.assertIn('비용', query)
        self.assertFalse(asks_location(query))

    def test_precise_type_does_not_trigger_repeated_type_question(self):
        for query in ('독감 어디서 맞아?', '폐렴구균 백신 접종 장소', 'B형간염 접종하는 곳',
                      '대상포진 백신 맞는곳', '코로나 백신 접종 장소', '예방접종실 위치'):
            self.assertIsNone(build_clarification(query), query)

    def test_location_match_is_not_incidental_hospital_mention(self):
        for body in ('과거' + HISTORY, '대상 : 보건소에서 무료로 접종했을 때 접종 불필요',
                     '장소 : 접종대상자만 접종', '보건소 백신 접종 대상 안내'):
            self.assertFalse(has_location(body), body)
        self.assertTrue(has_location('접종장소 : 전국 지정 위탁의료기관'))
        self.assertTrue(has_location('예방접종은 사하구보건소에서 접종 가능합니다.'))

    def test_colonless_place_row_is_paired_but_unrelated_cells_are_not(self):
        self.assertIn('장소: 사하구보건소 1층 예방접종실', location_source_units(BODY.splitlines()))
        self.assertEqual(location_source_units(['장소', '종류', 'B형 간염']), ['장소', '종류', 'B형 간염'])
        self.assertFalse(has_location('장소\n장소 : 보건소 접종 대상'))
        self.assertFalse(has_location('장소\n보건소 보건교육실(3층)\n보건소 별관교육실(2층)'))

    def test_location_query_cannot_be_answered_with_eligibility_exception(self):
        result = concise_source_answer('백신 접종 장소', '> 과거' + HISTORY,
            [{'metadata': {'url': 'https://www.saha.go.kr/health/other'}}], {'백신'})
        self.assertTrue(result['is_clarification'])
        self.assertNotIn('접종 불필요', result['answer'])

    def test_pneumococcal_place_keeps_age_program_scope_and_no_health_center_injection(self):
        result = summary('폐렴구균 백신 접종 장소')
        self.assertFalse(result['is_clarification'])
        for fact in ('65세 이상', '접종장소', '보건소 접종 미운영', '전국 지정 위탁의료기관'):
            self.assertIn(fact, result['answer'])
        self.assertNotIn('접종 불필요', result['answer'])
        self.assertNotIn('1층', result['answer'])
        self.assertLess(len(result['answer']), 180)

    def test_influenza_place_keeps_geographic_restriction_and_annual_provider_notice(self):
        result = summary('독감 어디서 맞아?')
        self.assertFalse(result['is_clarification'])
        for fact in ('접종장소', '부산시 지정 위탁의료기관만 가능', '대상 :', '직접 주사 안됨', '매년 독감접종'):
            self.assertIn(fact, result['answer'])
        self.assertNotIn('폐렴구균', result['answer'])
        self.assertNotIn('접종 불필요', result['answer'])
        self.assertLess(len(result['answer']), 300)

    def test_hepatitis_place_uses_first_table_not_another_vaccine_program(self):
        result = summary('B형간염 접종 장소')
        self.assertFalse(result['is_clarification'])
        self.assertIn('사하구보건소 1층 예방접종실', result['answer'])
        self.assertNotIn('전국 지정', result['answer'])

    def test_incomplete_structure_does_not_fall_back_to_wrong_program(self):
        for body in (BODY.replace('인플루엔자 예방접종\n', '독감 안내\n'),
                     BODY.replace('※ 지정의료기관은 매년 독감접종 시작전 공고 예정', '')):
            self.assertTrue(summary('독감 접종 장소', body)['is_clarification'])
        self.assertEqual(focused_section('B형간염 접종 장소', ADULT_VACCINE_URL,
            BODY.replace('B형 간염\n', '')), '')

    def test_other_products_or_populations_do_not_inherit_senior_ppsv23_place(self):
        for query in ('어린이 폐렴구균 백신 접종 장소', '40세 폐렴구균 접종 장소',
                      '폐렴구균 20가 백신 접종 장소', '임산부 독감 접종 장소', '코로나 백신 접종 장소'):
            self.assertEqual(focused_section(query, ADULT_VACCINE_URL, BODY), '', query)

    def test_named_vaccine_selects_official_url_without_routing_unrelated_services(self):
        for query in ('독감 접종 장소', '폐렴구균 접종 하는곳', 'B형간염 접종 장소'):
            self.assertEqual(match_official_page(query), ADULT_VACCINE_URL)
        with patch('chatbot.faq_targets._targets', return_value=[]):
            for query in ('독감 치료 병원 위치', '어린이 폐렴구균 접종 장소', '코로나 백신 접종 장소'):
                self.assertIsNone(match_official_page(query), query)

    def test_general_health_center_location_uses_directions_not_a_program_room(self):
        for query in ('보건소 위치 알려줘', '사하구 보건소 주소', '보건소 어디야?'):
            self.assertEqual(match_official_page(query), 'https://www.saha.go.kr/health/contents.do?mId=0103000000')
        with patch('chatbot.faq_targets._targets', return_value=[]):
            self.assertIsNone(match_official_page('보건소 당뇨교실 위치'))

    def test_location_and_generic_vaccine_words_do_not_hide_specific_type(self):
        for query in ('백신 접종 하는곳 알려줘 독감', '독감 어디서 맞아?'):
            self.assertEqual(fallback_keywords(query), {'인플루엔자'})
        self.assertEqual(fallback_keywords('보건소 위치 알려줘'), {'보건소'})
        self.assertEqual(fallback_keywords('구민문화회관 위치 알려줘'), {'구민문화회관'})
        self.assertFalse(asks_location('공장 소음 신고'))
        self.assertFalse(asks_location('공장소음 신고'))

    def test_source_selection_skips_history_only_page_and_uses_actual_place(self):
        pages = {'history': '백신 과거' + HISTORY,
                 'place': '백신 접종 안내\n접종장소 : 전국 지정 위탁의료기관'}
        class Query:
            def select(self, *_): return self
            def eq(self, _field, url): self.url = url; return self
            def limit(self, *_): return self
            def execute(self): return type('Rows', (), {'data': [{'content': pages[self.url]}]})()
        class Client:
            def table(self, *_): return Query()
        docs = [{'content': body, 'metadata': {'url': url, 'title': '백신 안내', 'source_type': 'official_page'}}
                for url, body in pages.items()]
        answer, used = build_source_answer(docs, Client(), query='백신 접종 장소', topic_keywords={'백신'})
        self.assertEqual(used, [docs[1]])
        self.assertIn('접종장소', answer)


if __name__ == '__main__':
    unittest.main()
