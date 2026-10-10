import unittest

from chatbot.answer_completion import balanced, complete_source_units
from chatbot.answer_enrichment import enrich_answer
from chatbot.concise_answers import MAX_BRIEF_LENGTH, concise_source_answer, _source_units, section_bounds
from chatbot.grounded_planner import eligible_ids, render_plan, prepare_evidence, plan_context
from chatbot.question_intent import location_source_units
from chatbot.query_subject import query_keywords


CLINIC = '\n'.join([
    '금연', '금연클리닉 운영',
    '흡연자를 대상으로 금연 상담 및 보조제 지원 등을 통해 금연 실천율을 높이고 건강한 삶을 살아갈 수 있도록 함',
    '기간', '연중 월-금요일 09:00 ~ 18:00 (점심시간 12:00~13:00 제외)',
    '청소년은 예약 필수', '장소', '사하구보건소 2층 통합건강증진센터 내 금연클리닉',
    '대상', '금연을 희망하는 지역주민', '문의', '사하구 보건소 금연클리닉 ☎ 051) 220-5716, 5717',
    '금연클리닉 대상자 등록 후 6개월간 서비스 제공',
    '국가 금연상담전화 안내 ▹평일 09:00~22:00, 주말/공휴일 09:00~18:00',
    '국가 금연상담전화 안내', '금연을 원하는 사람들에게 30일 금연 및 금연유지 프로그램 제공',
    '이동 금연 클리닉(찾아가는 금연 지원 서비스)',
    '대상 : 금연 희망자 10명 이상인 관내 사업장, 학교, 기타 생활터 등',
    '장소 : 관내 사업장 및 학교',
])
HOURS = '진료시간 : 평일(월∼금) 오전 9:00 ∼ 오후 6:00 ※ 점심시간 : 12시~13시'
CAUTION = '※ 단, 검사 및 예방접종은 소요시간이 있으므로 최소한 업무종료 30분 전까지는 방문하셔야합니다.'
ADDRESS = '위 치 : 부산광역시 사하구 하신중앙로 185(신평동, 사하구 제2청사 보건소동)'
DIRECTIONS = '\n'.join(['찾아오시는길', HOURS, CAUTION, ADDRESS])
AUDIENCE = '- 대상 : 금연을 희망하는 지역주민'
AUDIENCE_QUERY = '사하구보건소 금연클리닉은 누가 이용할 수 있나요?'
COMPOUND_QUERY = '사하구보건소 진료시간과 위치는 어떻게 되나요?'


def document(body, title, url):
    return {'content': body, 'metadata': {'title': title, 'url': url,
            'source_type': 'crawled_page', 'category': '보건소'}}


class AnswerEnrichmentTests(unittest.TestCase):
    def test_target_answer_adds_real_service_and_venue_with_reservation_condition(self):
        answer = enrich_answer(AUDIENCE_QUERY, AUDIENCE, CLINIC, {'금연', '보건소'}, '금연')
        for fact in ('금연을 희망하는 지역주민', '금연 상담 및 보조제 지원', '2층 통합건강증진센터', '청소년은 예약 필수'):
            self.assertIn(fact, answer)
        for unrelated in ('22:00', '30일', '10명', '관내 사업장'):
            self.assertNotIn(unrelated, answer)
        self.assertLessEqual(len(answer), MAX_BRIEF_LENGTH)

    def test_model_and_source_fallback_both_enrich_without_additional_model_call(self):
        doc = document(CLINIC, '금연', 'https://www.saha.go.kr/health/contents.do?mId=0404000000')
        units = _source_units(CLINIC.splitlines())
        index = next(i for i, u in enumerate(units) if u.startswith('대상 : 금연을 희망'))
        packet = {'document': doc, 'body': CLINIC, 'section_body': CLINIC, 'units': units}
        packet['eligible_ids'] = eligible_ids(AUDIENCE_QUERY, packet, {'금연', '보건소'})
        model = render_plan(AUDIENCE_QUERY, {'mode': 'answer', 'source': 0, 'units': [index]}, [packet], {'금연', '보건소'})
        fallback = concise_source_answer(AUDIENCE_QUERY, '\n'.join('> ' + u for u in CLINIC.splitlines()), [doc], {'금연', '보건소'})
        for result in (model, fallback):
            self.assertIsNotNone(result)
            self.assertIn('보조제 지원', result['answer'])
            self.assertIn('2층 통합건강증진센터', result['answer'])
            self.assertIn('예약 필수', result['answer'])
            self.assertIn('10명', result['answer_details'])
            self.assertNotIn('10명', result['answer'])

    def test_compound_question_gets_both_fields_and_keeps_visit_caution(self):
        answer = enrich_answer(COMPOUND_QUERY, '- ' + HOURS + '\n- ' + CAUTION,
                               DIRECTIONS, {'보건소'}, '찾아오시는길')
        for fact in ('오전 9:00', '하신중앙로 185', '업무종료 30분 전'):
            self.assertIn(fact, answer)
        doc = document(DIRECTIONS, '찾아오시는길', 'https://www.saha.go.kr/health/contents.do?mId=0103000000')
        units = _source_units(DIRECTIONS.splitlines())
        packet = {'document': doc, 'body': DIRECTIONS, 'units': units}
        self.assertIn(3, eligible_ids(COMPOUND_QUERY, packet, {'보건소'}))
        result = render_plan(COMPOUND_QUERY, {'mode': 'answer', 'source': 0, 'units': [1]}, [packet], {'보건소'})
        self.assertIn('하신중앙로 185', result['answer'])
        self.assertIn('업무종료 30분 전', result['answer'])

    def test_missing_requested_location_is_stated_without_inventing_address(self):
        answer = enrich_answer(COMPOUND_QUERY, '- ' + HOURS, HOURS, {'보건소'})
        self.assertIn('위치는 이 자료에서 명확히 확인되지 않았습니다.', answer)
        self.assertNotIn('하신중앙로', answer)

    def test_single_hours_question_does_not_expand_to_unrequested_location(self):
        answer = enrich_answer('보건소 진료시간 알려줘', '- ' + HOURS, DIRECTIONS, {'보건소'})
        self.assertNotIn('하신중앙로', answer)

    def test_service_question_adds_visit_information_from_same_program(self):
        core = '- 금연클리닉 대상자 등록 후 6개월간 서비스 제공'
        query = '금연클리닉에서 어떤 서비스를 제공하나요?'
        keywords = query_keywords(query, ['금연', '클리닉', '서비스', '제공'])
        self.assertEqual(keywords, {'금연', '클리닉'})
        answer = enrich_answer(query, core, CLINIC, keywords, '금연')
        self.assertIn('2층 통합건강증진센터', answer)
        self.assertIn('09:00 ~ 18:00', answer)
        self.assertIn('예약 필수', answer)
        self.assertNotIn('22:00', answer)

    def test_repeated_targets_in_different_programs_are_not_joined(self):
        body = CLINIC.replace('대상 : 금연 희망자 10명 이상인 관내 사업장, 학교, 기타 생활터 등',
                              '대상 : 금연을 희망하는 지역주민')
        self.assertEqual(enrich_answer(AUDIENCE_QUERY, AUDIENCE, body, {'금연'}, '금연'), AUDIENCE)

    def test_different_service_or_omitted_section_does_not_supply_extra_facts(self):
        body = '검사 프로그램\n대상 : 지역주민\n[…]\n장소 : 사하구보건소 2층 상담실'
        core = '- 대상 : 지역주민'
        self.assertEqual(enrich_answer('검사 프로그램은 누가 이용하나요?', core, body, {'검사'}, '검사'), core)
        self.assertEqual(enrich_answer('금연클리닉은 누가 이용하나요?', core, body, {'금연'}, '검사'), core)

    def test_length_limit_keeps_additional_fact_and_its_condition_together(self):
        core = '- 대상 : 지역주민\n' + '핵심 안내. ' * 63
        body = '검사 프로그램\n대상 : 지역주민\n장소 : 사하구보건소 2층 상담실\n청소년은 반드시 사전 예약이 필요합니다.'
        self.assertLessEqual(len(core), MAX_BRIEF_LENGTH)
        self.assertGreater(len(core + '\n- 장소 : 사하구보건소 2층 상담실\n- 청소년은 반드시 사전 예약이 필요합니다.'), MAX_BRIEF_LENGTH)
        answer = enrich_answer('검사 프로그램은 누가 이용하나요?', core, body, {'검사'}, '검사')
        self.assertEqual(answer, core)

    def test_conflicting_program_venues_are_not_added(self):
        body = '검사 프로그램\n대상 : 지역주민\n장소 : 사하구보건소 2층 상담실\n장소 : 다른 보건소 검사실'
        core = '- 대상 : 지역주민'
        self.assertEqual(enrich_answer('검사 프로그램은 누가 이용하나요?', core, body, {'검사'}, '검사'), core)

    def test_explicit_mobile_program_uses_its_own_target_not_local_clinic_target(self):
        doc = document(CLINIC, '금연', 'https://www.saha.go.kr/health/contents.do?mId=0404000000')
        query = '이동 금연 클리닉은 누가 이용하나요?'
        result = concise_source_answer(query, '\n'.join('> ' + u for u in CLINIC.splitlines()), [doc], {'금연'})
        self.assertIn('10명 이상', result['answer'])
        self.assertNotIn('2층 통합건강증진센터', result['answer'])

    def test_long_page_keeps_requested_program_visible_to_model(self):
        body = CLINIC + '\n금연 교육 프로그램\n' + '\n'.join(
            '금연클리닉 안내 : 금연클리닉 교육은 예약제로 운영합니다.' for _ in range(40))
        doc = document(body, '금연', 'https://www.saha.go.kr/health/contents.do?mId=0404000000')
        keywords = {'금연', '클리닉'}
        packets = prepare_evidence(AUDIENCE_QUERY, [doc], None, keywords)
        for packet in packets:
            packet['eligible_ids'] = eligible_ids(AUDIENCE_QUERY, packet, keywords)
        context, shown = plan_context(packets)
        self.assertEqual(len(shown), 1)
        self.assertIn('금연을 희망하는 지역주민', context)
        self.assertNotIn('22:00', context)
        self.assertNotIn('금연클리닉 교육은 예약제로', context)

    def test_phone_notation_does_not_join_following_program_heading(self):
        phone = '사하구 보건소 금연클리닉 ☎ 051) 220-5716, 5717'
        self.assertTrue(balanced(phone))
        self.assertFalse(balanced('청소년은 사전 예약(보호자 동반'))
        units = complete_source_units([phone, '국가 금연상담전화 안내', '금연유지 프로그램 제공'])
        self.assertEqual(units, [phone, '국가 금연상담전화 안내', '금연유지 프로그램 제공'])

    def test_heading_with_hours_starts_new_service_boundary(self):
        units = _source_units(location_source_units(CLINIC.splitlines()))
        target = next(i for i, u in enumerate(units) if u.startswith('대상 : 금연을 희망'))
        _, end = section_bounds(units, target)
        self.assertTrue(units[end].startswith('국가 금연상담전화 안내 ▹'))


if __name__ == '__main__':
    unittest.main()
