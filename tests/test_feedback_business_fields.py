import unittest
from unittest.mock import Mock

from chatbot.answer_goal import answer_goal, requested_goals
from chatbot.candidate_search import search_candidates
from chatbot.faq_targets import confident_official_page
from chatbot.response_helpers import build_clarification
from chatbot.source_scope import normalize_plain_source, focus_terms
from chatbot.structured_answers import field_matches, structured_brief
from chatbot.evidence import is_service_source
from chatbot.source_warnings import reviewed_source


class BusinessFieldTests(unittest.TestCase):
    def test_registered_business_never_falls_back_to_another_business(self):
        query='아파트 등 공동주택 관리에 필요한 정보는 어디에서 확인하나요?'
        url=confident_official_page(query)
        retriever=Mock()
        retriever._content_keywords.return_value={'공동주택'}
        retriever.search_official_url.return_value={'results':[], 'degraded':False, 'reason':None}
        result=search_candidates(retriever, query)
        retriever.search_official_url.assert_called_once_with(query, url, k=15)
        self.assertEqual(result['results'], [])
        retriever.search_crawled_pages.assert_not_called()
        self.assertFalse(result['retrieval']['vector_invoked'])

    def test_word_spacing_does_not_change_registered_name_guide(self):
        self.assertEqual(confident_official_page('여권 영문성명은 어떻게 표기하나요?'),
                         confident_official_page('여권 영문 성명은 어떻게 표기 하나요?'))
        self.assertIsNotNone(confident_official_page('여권 영문성명은 어떻게 표기하나요?'))
        self.assertIsNone(confident_official_page('공동주택 관리비를 할인받을 수 있나요?'))

    def test_arrears_consequences_are_not_a_deadline_question(self):
        query='지방세를 기한 내에 내지 않으면 어떤 불이익이 있나요?'
        self.assertEqual(requested_goals(query), ('conditions',))
        self.assertFalse(field_matches('conditions', '처리기간: 접수 후14일', query))
        self.assertTrue(field_matches('conditions', '지방세징수법: 재산 압류 및 공매', query))

    def test_unfair_assessment_requests_a_remedy_not_a_generic_service_catalogue(self):
        query='부당한 지방세 처분 때문에 어려움이 있을 때 도움을 받을 수 있나요?'
        self.assertEqual(answer_goal(query), 'method')
        self.assertTrue(field_matches('method', '신청방법: 고충민원 신청서를 작성하여 납세자보호관에게 제출', query))
        self.assertNotEqual(answer_goal('세무사 비용이 부담되는데 무료 세무상담을 받을 수 있나요?'), 'method')

    def test_name_format_cannot_be_replaced_by_application_website(self):
        query='여권 영문성명은 어떻게 표기하나요?'
        self.assertFalse(field_matches('method', '신청 주소: https://www.gov.kr', query))
        self.assertTrue(field_matches('method', '표기방법: 영문성명은 반드시 대문자로 표기', query))

    def test_location_independence_needs_an_explicit_source_condition(self):
        query='여권은 주소지와 관계없이 신청할 수 있나요?'
        self.assertTrue(field_matches('conditions', '여권 신청은 주소지와 관계없이 전국 구(군) 어디서나 가능합니다.', query))
        self.assertFalse(field_matches('conditions', '신청조건: 본인 직접 방문', query))

    def test_valuation_reference_date_is_not_publication_date(self):
        query='개별공시지가는 언제 공시되나요?'
        self.assertFalse(field_matches('schedule', '정의: 매년1월1일 기준 단위면적당 가격', query))
        self.assertFalse(field_matches('schedule', '국세 — 적용개시일: 1990.5.1', query))
        self.assertTrue(field_matches('schedule', '공시일: 4월30일', query, '공시일'))

    def test_definition_heading_owns_a_noun_ending_definition(self):
        body=normalize_plain_source('## 임대사업자 등록안내\n### 민간임대 등록제도란\n개인이 주택을 등록하고 공적 의무를 준수하면 세제지원을 제공받는 제도', '임대사업자 등록안내')
        self.assertIn('정의: 개인이 주택', body)
        self.assertEqual(normalize_plain_source(body, '임대사업자 등록안내'), body)

    def test_online_channel_does_not_leak_into_next_program(self):
        body=normalize_plain_source('## 신청\n(온라인)\n공식 사이트\n(오프라인) 은행 창구\n### 다른 사업\n(온라인)\n### 새 사업\n별도 안내', '신청')
        self.assertIn('이용방법: (온라인) 공식 사이트', body)
        self.assertIn('이용방법: (오프라인) 은행 창구', body)
        self.assertNotIn('이용방법: (온라인) 별도 안내', body)
        self.assertEqual(normalize_plain_source(body, '신청'), body)

    def test_provider_and_example_assets_are_not_extra_requested_facts(self):
        self.assertNotIn('센터', focus_terms('일자리지원센터 구직 등록 방법'))
        self.assertNotIn('차량', focus_terms('차량 취득세 신고 기한은 언제인가요?'))
        self.assertNotIn('컴퓨터', focus_terms('디지털·컴퓨터 교육 받을 수 있나요?'))
        self.assertIn('코딩', focus_terms('디지털·컴퓨터 코딩 교육 받을 수 있나요?'))

    def test_information_availability_keeps_the_source_applicant_condition(self):
        query='조상 땅을 찾을 수 있는 서비스가 있나요?'
        self.assertEqual(answer_goal(query), 'services')
        body='## 조상 땅 찾기\n본인 또는 사망한 직계 존비속의 토지소유 정보 제공 서비스 입니다.\n### 신청자격\n신청자격: 본인 또는 상속인, 대리인'
        result=structured_brief(query, {'metadata':{'title':'조상 땅 찾기'}}, body, {'조상땅'})
        self.assertIsNotNone(result)
        self.assertIn('상속인', result['answer'])
        self.assertIn('직계', result['answer'])

    def test_availability_shortcut_rejects_another_services_overview(self):
        doc={'metadata':{'title':'조상 땅 찾기'}}
        body='## 조상 땅 찾기\n토지소유 정보를 제공하는 서비스 입니다.\n신청자격: 본인 또는 상속인'
        self.assertIsNone(structured_brief('주차 서비스를 받을 수 있나요?', doc, body, {'주차'}))

    def test_nonliteral_subject_needs_both_private_rental_and_housing_proof(self):
        query='민간임대주택 임대사업자 등록제도는 무엇인가요?'
        good={'content':'## 임대사업자 등록\n### 민간임대 등록제도란\n개인이 주택을 등록하고 공적 의무를 준수하는 제도', 'metadata':{'title':'임대사업자 등록안내'}}
        self.assertTrue(is_service_source(query, good, {'민간임대주택'}))
        bad={**good,'content':'## 장비 임대\n민간임대 장비 대여 안내'}
        self.assertFalse(is_service_source(query, bad, {'민간임대주택'}))

    def test_acquisition_intro_cannot_override_type_specific_deadlines(self):
        body=('취득세는 매매, 상속 등 취득한 날부터60일 이내 신고합니다.\n'
              '신고 및 납부기한: 일반60일, 무상취득3개월, 상속6개월')
        safe,meta=reviewed_source(body, {'url':'https://www.saha.go.kr/portal/contents.do?mId=0105020400'})
        self.assertNotIn('취득세는', safe)
        self.assertIn('무상취득3개월', safe)
        self.assertEqual(meta['unverified_fields'], [])

    def test_sign_type_is_a_needed_condition_not_a_new_button(self):
        question=build_clarification('가게 간판을 설치하기 전에 허가나 신고가 필요한가요?')
        self.assertIn('간판의 종류', question['answer'])
        self.assertEqual(question['suggested_questions'], [])
        self.assertIsNone(build_clarification('벽면 간판5제곱미터 허가가 필요한가요?'))

    def test_navigation_labels_are_not_eligibility_facts_or_shared_parse_cache(self):
        from chatbot.source_pages import parsed_original
        html='<div id="conts"><h3>서비스 바로가기</h3><div class="link_box"><a href="/tax">지방세인터넷납부 바로가기</a><a href="/land">개별공시지가안내 바로가기</a></div></div>'
        row={'raw_html':html,'content':'fallback'}
        self.assertNotIn('지방세인터넷납부', parsed_original(row))
        self.assertIn('지방세인터넷납부', parsed_original(row, True))
        self.assertNotIn('지방세인터넷납부', parsed_original(row))
        from chatbot.evidence_decision import source_body
        self.assertIn('지방세인터넷납부', source_body({'_raw_page':row,'_include_navigation':True}))
        self.assertNotIn('지방세인터넷납부', source_body({'_raw_page':row}))

    def test_acknowledgement_to_type_question_keeps_the_topic_without_selecting_an_age(self):
        from chatbot.response_helpers import resolve_clarification_reply
        q='소방 교육 하는방법 알려줘'
        pending={**build_clarification(q), 'query':q}
        self.assertEqual(resolve_clarification_reply('어 맞아', pending), q)
        resolved=resolve_clarification_reply('아이는 8살', pending)
        self.assertIn('소방', resolved)
        self.assertIn('8살', resolved)

    def test_donation_channels_do_not_drop_the_residence_exclusion(self):
        query='고향사랑기부제는 어떻게 이용하나요?'
        body='## 고향사랑기부제\n개인(법인,단체기부불가)이 본인의 주소지를 제외한 지자체에 기부 가능\n(온라인)\n고향사랑e음 사이트\n(오프라인) 전국 NH농협은행을 통해 기부가능'
        result=structured_brief(query, {'metadata':{'title':'고향사랑기부제'}}, body, {'고향사랑기부'})
        self.assertIsNotNone(result)
        self.assertIn('주소지를 제외', result['answer'])
        self.assertIn('법인,단체기부불가', result['answer'])

    def test_acquisition_deadline_is_not_a_permission_check(self):
        self.assertEqual(answer_goal('차량을 취득하면 취득세는 언제까지 신고해야 하나요?'), 'schedule')
        self.assertNotIn('차량', focus_terms('차량을 취득하면 취득세는 언제까지 신고해야 하나요?'))


if __name__ == '__main__':
    unittest.main()
