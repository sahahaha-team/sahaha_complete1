"""Field corrections preserve the established service without inventing facts."""
import unittest
from chatbot.response_helpers import build_contextual_search_query, build_clarification
from chatbot.answer_goal import answer_goal
from chatbot.faq_targets import match_official_page
from chatbot.vaccination import vaccine_kind


def follow(previous, reply):
    return build_contextual_search_query(reply, [{'role': 'user', 'content': previous}])


class FeedbackFollowupTests(unittest.TestCase):
    def test_explicit_field_replacement_discards_the_rejected_request(self):
        for previous in ('미성년자 여권 준비물 12세 부모', '작은도서관 교육 프로그램 예약 방법'):
            with self.subTest(previous=previous):
                query = follow(previous, '신청 말고 장소 알려줘')
                self.assertIn(previous.split()[0], query)
                self.assertEqual(answer_goal(query), 'location')
                self.assertNotIn('준비물', query)
                self.assertNotIn('신청 말고', query)

    def test_age_reply_retains_the_named_education_and_latest_age(self):
        query = follow('소방특화 들락날락 체험 예약 방법', '아이는 8살')
        self.assertIn('소방', query)
        self.assertIn('8살', query)
        updated = follow(query, '아니 12살이야')
        self.assertIn('소방', updated)
        self.assertIn('12살', updated)
        self.assertNotIn('8살', updated)

    def test_vaccine_correction_replaces_kind_and_keeps_location_goal(self):
        query = follow('보건소 폐렴구균 예방접종 어디서 해?', '아니 독감이야')
        self.assertEqual(vaccine_kind(query), '인플루엔자')
        self.assertIn('접종', query)
        self.assertEqual(answer_goal(query), 'location')
        self.assertNotIn('폐렴구균', query)

    def test_correction_with_no_previous_topic_does_not_create_one(self):
        self.assertNotIn('접종', follow('', '아니 독감이야'))
        self.assertNotIn('여권', follow('', '아이는 8살'))

    def test_complete_new_service_is_not_a_profile_correction(self):
        query = follow('소방 체험 예약 방법 8살', '12살 여권 준비물 알려줘')
        self.assertNotIn('소방', query)
        self.assertIn('여권', query)

    def test_specific_facility_routes_variants_to_its_official_page(self):
        url = 'https://www.saha.go.kr/reserve/contents.do?mId=1207000000'
        for query in ('소방특화 들락날락 예약 방법 알려줘', '소방특화 들락날락 위치', '소방 특화 들락날락 12살 예약'):
            self.assertEqual(match_official_page(query), url)
        self.assertNotEqual(match_official_page('공동주택 관리자 소방교육 일정'), url)
        self.assertNotEqual(match_official_page('여권 소방특화 준비물'), url)
        self.assertNotEqual(match_official_page('을숙도 들락날락 예약 방법'), url)

    def test_facility_name_is_not_an_extra_condition_in_source_selection(self):
        from chatbot.source_scope import focus_terms
        self.assertNotIn('특화', focus_terms('소방특화 들락날락 예약 방법'))
        self.assertIn('훼손', focus_terms('소방특화 들락날락 훼손된 예약증 처리 방법'))

    def test_registered_page_can_establish_ownership_with_a_generic_heading(self):
        from chatbot.candidate_search import complete_direct_candidates
        doc = {'content': '## 이용안내\n이용대상: 4세 이상 13세 이하 어린이\n신청방법: 홈페이지에서 예약 신청 가능합니다.\n### 공간안내\n1F 소방안전교육센터(심폐소생술 체험관)',
               'metadata': {'title': '이용안내', 'source_type': 'crawled_page',
                            'url': 'https://www.saha.go.kr/reserve/contents.do?mId=1207000000'}}
        query = '소방특화 들락날락 예약 방법 알려줘'
        self.assertEqual(complete_direct_candidates(query, [doc], {'소방'}), [doc])
        other = {**doc, 'metadata': {**doc['metadata'], 'url': 'https://www.saha.go.kr/portal/contents.do?mId=other'}}
        self.assertEqual(complete_direct_candidates(query, [other], {'소방'}), [])
        unrelated = {**doc, 'content': '## 이용안내\n신청방법: 홈페이지에서 신청 가능합니다.'}
        self.assertEqual(complete_direct_candidates(query, [unrelated], {'소방'}), [])

    def test_physical_location_never_uses_an_online_application_address(self):
        from chatbot.structured_answers import field_matches
        self.assertFalse(field_matches('location', '신청 주소: https://www.gov.kr/portal/main', '여권 장소 알려줘'))
        self.assertTrue(field_matches('location', '신청 주소: https://www.gov.kr/portal/main', '온라인 여권 신청 주소'))
        self.assertTrue(field_matches('location', '주소: 부산 사하구 장평로 270', '소방 체험 장소 알려줘'))

    def test_broad_tax_list_cannot_borrow_one_child_taxs_payment_schedule(self):
        from chatbot.evidence import is_service_source
        doc = {'content': '자동차세는 지방세입니다. 납부는 매년 6월과 12월입니다.',
               'metadata': {'title': '자동차세', 'url': 'https://www.saha.go.kr/portal/contents.do?mId=test'}}
        self.assertFalse(is_service_source('지방세 종류 알려줘', doc, {'지방세'}))

    def test_broad_service_queries_ask_one_scope_question(self):
        for query in ('사하구 복지 서비스에는 무엇이 있나요?', '사하구보건소에서는 어떤 업무를 이용할 수 있나요?', '사하구의 주요 민원 서비스에는 무엇이 있나요?'):
            self.assertIsNotNone(build_clarification(query), query)

    def test_unspecified_vaccine_method_asks_kind_instead_of_certificate(self):
        result = build_clarification('예방접종은 전화로만 신청할 수 있어?')
        self.assertIsNotNone(result)
        self.assertIn('백신', result['answer'])

    def test_general_resident_course_can_narrow_once_by_age(self):
        self.assertIn('어린이', build_clarification('소방교육 신청 방법 (확인대상: 일반 주민)')['answer'])
        self.assertIsNone(build_clarification('소방교육 신청 방법 (확인대상: 일반 주민) 아이는 8살'))

    def test_generic_course_clarifies_before_selecting_a_child_facility(self):
        from chatbot.response_helpers import resolve_clarification_reply
        pending = {**build_clarification('소방 교육 하는방법 알려줘'), 'query':'소방 교육 하는방법 알려줘'}
        self.assertTrue(pending['audience_question'])
        resolved = resolve_clarification_reply('아니 일반 주민이야', pending)
        self.assertIn('(확인대상:일반주민)', resolved.replace(' ', ''))
        next_question = build_clarification(resolved)
        age_query = resolve_clarification_reply('아이는 8살', {**next_question, 'query':resolved})
        self.assertIn('8살', age_query)
        self.assertIsNone(build_clarification(age_query))

    def test_internal_profile_is_not_a_requested_detail_but_remains_a_constraint(self):
        from chatbot.source_scope import focus_terms
        self.assertNotIn('일반', focus_terms('소방교육 신청 방법 (확인대상: 일반 주민) 아이는 8살'))
        self.assertNotIn('교육', focus_terms('소방교육 신청 방법 (확인대상: 일반 주민) 아이는 8살'))
        from chatbot.evidence import is_service_source
        document = {'content': '## 소방교육\n대상: 어린이\n신청방법: 예약', 'metadata': {'title': '소방교육'}}
        self.assertFalse(is_service_source('소방교육 (확인대상: 공동주택 경비책임자)', document, {'소방'}))

    def test_selection_criteria_and_levied_vehicle_are_eligibility_questions(self):
        from chatbot.structured_answers import field_matches
        for query in ('기초생활보장 수급자는 어떤 기준으로 선정되나요?', '환경개선부담금은 어떤 차량에 부과되나요?'):
            self.assertEqual(answer_goal(query), 'eligibility')
        self.assertTrue(field_matches('eligibility', '부과대상: 등록된 경유사용 차량'))

    def test_heading_owns_an_existing_labelled_tax_subject(self):
        from chatbot.source_scope import normalize_plain_source, is_field_heading
        body = normalize_plain_source('## 부담금\n### 부과대상\n자동차: 등록된 경유사용 차량\n### 납기\n3월', '부담금')
        self.assertIn('부과대상: 자동차: 등록된 경유사용 차량', body)
        self.assertTrue(is_field_heading('부과대상'))
        self.assertEqual(normalize_plain_source(body, '부담금'), body)

    def test_conflicting_guardian_amounts_are_quarantined_without_removing_general_rules(self):
        from chatbot.source_warnings import reviewed_source
        body = ('선정기준: 소득인정액이 급여종류별 선정기준 이하인 사람\n'
                '부양의무자 소득 연 1.3억원 일반재산 12억원 초과 제외\n'
                '다만 고소득(연1억) 고재산(9억) 부양의무자 기준 적용\n'
                '신청절차: 주민등록상 주소지 동에 신청')
        safe, meta = reviewed_source(body, {'url':'https://www.saha.go.kr/portal/contents.do?mId=0501000000'})
        self.assertIn('소득인정액', safe)
        self.assertIn('신청절차', safe)
        self.assertNotIn('억원', safe)
        self.assertNotIn('9억', safe)
        self.assertEqual(meta['source_review_status'], 'conflict')

    def test_amount_review_preserves_same_paragraph_eligibility_and_exemptions(self):
        from chatbot.source_warnings import reviewed_source
        body = ('선정기준: 소득인정액이 기준 이하. 생계급여, 주거급여, 교육급여는 부양능력 판정기준 적용하지 않으나 단, 생계급여는 부양의무자의 소득 연 1.3억원·일반재산 12억원 초과 제외\n'
                '부양의무자 관련 개정사항: 고소득(연1억) 고재산(9억) 확인 필요')
        safe, meta = reviewed_source(body, {'url':'https://www.saha.go.kr/portal/contents.do?mId=0501010000'})
        self.assertIn('소득인정액', safe)
        self.assertIn('주거급여', safe)
        self.assertIn('적용하지 않으나', safe)
        self.assertIn('금액 기준 확인 필요', safe)
        self.assertNotIn('1.3억', safe)
        self.assertEqual(meta['source_review_status'], 'conflict')

    def test_general_eligibility_cannot_borrow_a_disability_benefit(self):
        from chatbot.evidence import is_service_source
        doc = {'content':'## 장애인 연금\n지원대상: 국민기초생활보장법 수급자 중 등록장애인', 'metadata':{'title':'제도시책'}}
        self.assertFalse(is_service_source('기초생활보장 수급자는 어떤 기준으로 선정되나요?', doc, {'기초생활보장'}))


if __name__ == '__main__':
    unittest.main()
