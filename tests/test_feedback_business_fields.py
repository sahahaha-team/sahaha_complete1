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
    def test_counselling_keeps_its_own_audience_not_a_sibling_grants(self):
        body=('## 구강보건\n### 틀니 지원\n대상: 65세 이상 수급자\n내용: 의치 비용 지원\n'
              '### 아동 사업\n대상: 초등학생\n내용: 구강건강서비스 제공(검사, 진료)\n'
              '### 구강보건실 운영\n대상: 사하구 지역주민\n내용: 생애주기별 구강보건상담 및 교육\n방법: 전화 예약 후 방문')
        result=structured_brief('구강건강 상담을 받을 수 있나요?', {'metadata':{'title':'구강보건'}},body,{'구강'})
        self.assertIn('지역주민',result['answer'])
        self.assertIn('상담',result['answer'])
        self.assertNotIn('수급자',result['answer'])
        self.assertNotIn('초등학생',result['answer'])

    def test_service_purpose_cannot_replace_requested_examination_and_counselling(self):
        body=('## 대사증후군 관리\n### 관리센터 운영\n목적: 맞춤형 건강관리 서비스를 제공\n대상: 19세 이상 구민\n'
              '일시: 월~금 09:00~18:00 사전 예약제로 검사 전날 밤10시부터 금식\n장소: 사하구보건소 2층 통합건강증진실\n'
              '내용: 위험요인 검사 및 맞춤상담 서비스 제공\n### 찾아가는 프로그램\n대상: 사업장\n내용: 위험요인 검사 및 맞춤상담 서비스 제공')
        result=structured_brief('대사증후군 검사를 받거나 건강상담을 받을 수 있나요?',{'metadata':{'title':'대사증후군 관리'}},body,{'대사증후군'})
        self.assertIn('위험요인 검사',result['answer'])
        self.assertIn('맞춤상담',result['answer'])
        self.assertIn('금식',result['answer'])
        self.assertNotIn('사업장',result['answer'])

    def test_test_list_membership_keeps_all_shared_applicant_conditions(self):
        body=('## 응시료 지원\n지원대상: 18~39세 중 아래 요건을 모두 충족하는 자\n- 거주기준: 1년 이상 거주\n'
              '- 근로이력: 미취업자 및 사업자등록사실이 없는 자\n지원내용: 연1회 응시료 지원\n'
              '구분: 지원 시험 종류\n어학: 토익, 토익스피킹, 텝스\n신청방법: 온라인 신청')
        q='토익이나 토익스피킹 응시료 지원을 받을 수 있나요?'
        result=structured_brief(q,{'metadata':{'title':'응시료 지원'}},body,{'응시료'})
        self.assertIsNotNone(result)
        for fact in ('토익스피킹','1년','미취업','사업자등록'):self.assertIn(fact,result['answer'])
        self.assertIsNone(structured_brief(q.replace('토익스피킹','가상시험'),{'metadata':{'title':'응시료 지원'}},body,{'응시료'}))

    def test_presenting_mood_can_access_explicit_resident_counselling_without_a_diagnosis(self):
        from chatbot.source_scope import unanswered_details
        q='우울감이나 정신건강 문제를 상담받을 곳이 있나요?'
        body='대상: 정신건강 상담을 원하는 사하구 주민\n위치: 구청'
        self.assertFalse(unanswered_details(q,body,'정신건강',{'정신건강'}))
        self.assertIn('우울감',unanswered_details(q,'대상: 등록 환자만','정신건강',{'정신건강'}))
        self.assertIn('우울감',unanswered_details('우울감 정신건강 약 복용량 알려줘',body,'정신건강',{'정신건강'}))

    def test_online_service_catalogue_retains_actual_online_routes_only(self):
        q='홈페이지에서 이용할 수 있는 전자민원 서비스에는 무엇이 있나요?'
        body=('## 민원실 이용안내\n온라인으로 민원 상담 및 접수를 하시려면 국민신문고를 이용해주시면 됩니다.\n'
              '주민등록등본 등의 서류 발급은 정부24로 온라인 발급하실수 있습니다.\n'
              '### 일반민원\n업무내용 : 인허가 접수 및 허가증 교부\n창구번호: 2번\n수수료: 600원')
        result=structured_brief(q, {'metadata':{'title':'민원실 이용안내'}}, body, {'전자민원'})
        self.assertIsNotNone(result)
        self.assertIn('국민신문고',result['answer'])
        self.assertIn('정부24',result['answer'])
        self.assertNotIn('허가증',result['answer'])
        self.assertNotIn('600원',result['answer'])
        self.assertIsNone(structured_brief(q, {'metadata':{'title':'전자민원'}}, '업무내용 : 인허가 접수 및 허가증 교부', {'전자민원'}))

    def test_elided_course_location_keeps_age_and_program_type(self):
        from chatbot.response_helpers import build_contextual_search_query
        from chatbot.dialogue_profile import child_course_conflict
        previous='소방 교육 하는방법 알려줘 아이는 8살'
        query=build_contextual_search_query('신청 말고 장소 알려줘', [{'role':'user','content':'아이는 8살','search_query':previous}])
        self.assertIn('교육', query)
        self.assertIn('8살', query)
        self.assertTrue(child_course_conflict(query, '대상: 공동주택 경비책임자\n장소: 구청'))
        self.assertFalse(child_course_conflict(query, '이용대상: 어린이\n장소: 체험관'))

    def test_spaced_library_program_is_only_a_navigation_hint(self):
        from chatbot.faq_targets import match_official_page
        self.assertEqual(match_official_page('작은 도서관 강좌 신청 어떻게 하나요?'),
                         'https://www.saha.go.kr/portal/contents.do?mId=0408030000')
        self.assertIsNone(match_official_page('큰 도서관에 코끼리 입양 신청 어떻게 하나요?'))
        from chatbot.candidate_search import complete_direct_candidates
        doc={'content':'## 작은도서관\n### 작은도서관 프로그램 운영 안내\n대상: 사하구민\n접수방법: 사하구 통합예약 온라인접수',
             'metadata':{'title':'작은도서관','url':'https://www.saha.go.kr/portal/contents.do?mId=0408030000','source_type':'crawled_page'}}
        self.assertEqual(len(complete_direct_candidates('작은도서관 강좌 신청 어떻게 하나요?', [doc], {'작은도서관'})),1)
        self.assertIn('코딩',focus_terms('작은도서관 코딩 강좌 신청 어떻게 하나요?'))

    def test_outdated_flu_age_does_not_remove_other_vaccine_fields(self):
        body=('### 폐렴구균\n대상 : 65세 이상인 자\n접종장소 : 전국 위탁의료기관\n'
              '### 인플루엔자 예방접종\n대상 : 12세 이하 어린이, 65세 이상 어르신 및 부산시 지자체 대상자\n'
              '접종장소 : 전국 지정 위탁의료기관 (지자체 대상자는 부산시 지정 기관)')
        safe,meta=reviewed_source(body, {'url':'https://www.saha.go.kr/health/contents.do?mId=0203020000'})
        self.assertNotIn('12세', safe)
        self.assertIn('대상 : 65세 이상인 자', safe)
        self.assertIn('지자체 대상자는 부산시', safe)
        self.assertIn('연령', meta['source_warning'])
        changed,_=reviewed_source(body.replace('12세','새 절기 확인'), {'url':'https://www.saha.go.kr/health/contents.do?mId=0203020000'})
        self.assertIn('새 절기 확인', changed)

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
