import unittest
from unittest.mock import patch

from chatbot.answer_completion import complete_source_units, starts_label
from chatbot.concise_answers import concise_source_answer
from chatbot.faq_targets import match_official_page
from chatbot.question_intent import asks_opening_hours, has_opening_hours
from chatbot.query_subject import fallback_keywords
from chatbot.source_answers import build_source_answer

HEALTH_URL = 'https://www.saha.go.kr/health/contents.do?mId=0103000000'
HEALTH_BODY = ('보건소 정보\n진료시간 :\n'
    '평일(월∼금) 오전 9:00 ∼ 오후 6:00 ※ 점심시간 : 12시~13시\n'
    '※ 단, 검사 및 예방접종은 소요시간이 있으므로 최소한 업무종료 30분 전까지는 방문하셔야합니다.\n'
    '위 치 :\n부산광역시 사하구 하신중앙로 185(신평동, 사하구 제2청사 보건소동)')


def brief(query, body=HEALTH_BODY, keywords=None):
    quote = '\n'.join('> ' + line for line in body.splitlines())
    return concise_source_answer(query, quote, [{'metadata': {'url': HEALTH_URL}}], keywords or {'보건소'})


class OpeningHoursTests(unittest.TestCase):
    def test_reported_query_returns_hours_lunch_and_early_arrival_condition(self):
        result = brief('보건소 여는시간 알려줘')
        self.assertFalse(result['is_clarification'])
        for value in ('평일', '9:00', '6:00', '12시~13시', '30분 전', '검사 및 예방접종'):
            self.assertIn(value, result['answer'])
        self.assertNotIn('하신중앙로', result['answer'])
        self.assertLess(len(result['answer']), 250)

    def test_colloquial_opening_and_closing_queries_use_same_verified_hours(self):
        for query in ('보건소 몇시에 열어?', '보건소 몇시까지 해?', '사하구 보건소 운영시간 알려줘'):
            with self.subTest(query=query):
                result = brief(query)
                self.assertFalse(result['is_clarification'])
                self.assertIn('진료시간', result['answer'])
                self.assertNotIn('하신중앙로', result['answer'])

    def test_short_numeric_hours_are_not_discarded(self):
        result = brief('보건소 운영시간', '보건소 안내\n운영시간:\n09:00~18:00')
        self.assertFalse(result['is_clarification'])
        self.assertIn('09:00~18:00', result['answer'])

    def test_clock_colons_do_not_split_a_label_from_its_value(self):
        units = complete_source_units(HEALTH_BODY.splitlines())
        self.assertIn('진료시간 : 평일(월∼금) 오전 9:00 ∼ 오후 6:00 ※ 점심시간 : 12시~13시', units)
        self.assertFalse(starts_label('평일 오전 09:00~18:00'))
        self.assertTrue(starts_label('2026년 운영시간: 09:00~18:00'))

    def test_new_source_field_is_not_merged_into_an_empty_label(self):
        units = complete_source_units(['위치:', '운영시간:', '09:00~18:00'])
        self.assertEqual(units, ['위치:', '운영시간: 09:00~18:00'])

    def test_address_only_source_cannot_answer_an_hours_question(self):
        result = brief('보건소 여는시간', '보건소 정보\n위치 : 부산광역시 사하구 하신중앙로 185')
        self.assertTrue(result['is_clarification'])
        self.assertNotIn('하신중앙로', result['answer'])

    def test_address_query_still_selects_address(self):
        result = brief('보건소 위치 알려줘', keywords={'보건소', '위치'})
        self.assertFalse(result['is_clarification'])
        self.assertIn('하신중앙로 185', result['answer'])
        self.assertNotIn('9:00', result['answer'])

    def test_operating_hours_and_processing_duration_are_distinct(self):
        self.assertTrue(asks_opening_hours('보건소 몇 시까지 해?'))
        for query in ('보건증 발급 소요시간', '여권 발급기간 며칠 걸려?', '검사 처리기간'):
            self.assertFalse(asks_opening_hours(query))
        self.assertFalse(has_opening_hours('보건증 처리기간 : 5일, 검사 소요시간 : 20분'))

    def test_search_subject_does_not_require_literal_operating_word(self):
        for query in ('보건소 여는시간 알려줘', '사하구 보건소 운영시간 알려줘', '보건소 몇시까지 해?'):
            self.assertEqual(fallback_keywords(query), {'보건소'})

    def test_time_wording_does_not_remove_part_of_a_facility_name(self):
        self.assertEqual(fallback_keywords('구민문화회관 운영시간 알려줘'), {'구민문화회관'})
        self.assertEqual(fallback_keywords('보건소 문 언제 열어?'), {'보건소'})

    def test_generic_health_hours_select_health_center_not_village_center(self):
        for query in ('보건소 여는시간 알려줘', '보건소 몇시에 열어?', '보건소 몇시까지 해?', '사하구 보건소 운영시간'):
            self.assertEqual(match_official_page(query), HEALTH_URL)

    def test_specific_services_do_not_inherit_general_health_hours(self):
        with patch('chatbot.faq_targets._targets', return_value=[]):
            for query in ('보건소 마을건강센터 운영시간', '보건소 예방접종 운영시간', '보건소 치매센터 운영시간',
                          '보건소 보건증 검사시간', '보건소 건강검진 운영시간'):
                self.assertIsNone(match_official_page(query), query)

    def test_method_query_cannot_be_answered_with_a_location_only(self):
        result = concise_source_answer('법률상담 신청 방법', '> 위치 : 사하구 무료법률상담실은 민원실에 있습니다.',
            [{'metadata': {}}], {'법률상담'})
        self.assertTrue(result['is_clarification'])
        self.assertNotIn('민원실', result['answer'])

    def test_source_selection_tries_next_page_when_first_has_no_hours(self):
        pages = {'location': '보건소 정보\n위치 : 사하구 하신중앙로 185', 'hours': HEALTH_BODY}
        class Query:
            def select(self, *_): return self
            def eq(self, _field, url): self.url = url; return self
            def limit(self, *_): return self
            def execute(self): return type('Rows', (), {'data': [{'content': pages[self.url]}]})()
        class Client:
            def table(self, *_): return Query()
        docs = [{'content': body, 'metadata': {'url': url, 'title': '보건소 안내', 'source_type': 'official_page'}}
                for url, body in pages.items()]
        answer, used = build_source_answer(docs, Client(), query='보건소 여는시간', topic_keywords={'보건소'})
        self.assertEqual(used, [docs[1]])
        self.assertIn('9:00', answer)


if __name__ == '__main__':
    unittest.main()
