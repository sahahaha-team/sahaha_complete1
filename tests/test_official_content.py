import unittest
from chatbot.official_content import official_html_text
from chatbot.structured_answers import structured_brief
from chatbot.evidence import is_answerable_document, is_service_source
from chatbot.privacy import mask_answer, detect_personal_info
from chatbot.grounded_planner import eligible_ids
from chatbot.concise_answers import named_section_bounds, _source_units


def doc(title='공식 안내'):
    return {'metadata': {'title': title, 'url': 'https://www.saha.go.kr/health/contents.do?mId=0201030000'}}


class OfficialContentTests(unittest.TestCase):
    def test_free_consultation_availability_keeps_explicit_free_proof(self):
        body=official_html_text('<div id="conts"><h3>마을세무사</h3><h4>마을세무사란?</h4><p>세금 고민 해결을 위해 무료 세무상담 서비스를 제공하는 제도입니다.</p><h4>이용대상</h4><p>취약계층 등 세무사 이용이 어려운 구민</p><h4>이용방법</h4><p>전화, 팩스, 이메일 상담</p></div>')
        result=structured_brief('무료 세무상담을 받을 수 있나요?',doc('마을세무사'),body,{'세무사'})
        self.assertIn('무료 세무상담',result['answer'])
        self.assertIn('취약계층',result['answer'])

    def test_program_operation_question_requests_actual_services(self):
        from chatbot.answer_goal import answer_goal
        self.assertEqual(answer_goal('운동이나 영양관리 프로그램도 운영하나요?'),'services')
        body='## 운동·영양프로그램\n### 건강관리 운동 영양 프로그램\n대상: BMI 25 이상 지역주민\n내용: 맞춤형 운동 및 영양 상담 제공'
        result=structured_brief('운동이나 영양관리 프로그램도 운영하나요?',doc('운동·영양프로그램'),body,{'운동','영양','관리','프로그램'})
        self.assertIn('운동 및 영양 상담',result['answer'])

    def test_support_list_names_only_requested_whole_items(self):
        from chatbot.structured_answers import requested_supported_items
        units=['구 분: 지원 시험 종류','어 학: ○ 토익, 텝스, 토익스피킹, 오픽']
        self.assertEqual(requested_supported_items('토익이나 토익스피킹 응시료 지원을 받을 수 있나요?',units),['지원 시험 — 어 학: 토익·토익스피킹'])
        self.assertEqual(requested_supported_items('토익스피킹 응시료 지원',units),['지원 시험 — 어 학: 토익스피킹'])
        self.assertEqual(requested_supported_items('없는시험 응시료 지원',units),[])
        self.assertEqual(requested_supported_items('토익 응시료 지원',['어 학: 토익, 텝스, 오픽']),[])

    def test_support_percentage_keeps_same_program_ceiling(self):
        body=official_html_text('<div id="conts"><h3>고위험 임산부 의료비지원</h3><h4>질환기준</h4><p>질환별 기준 적용</p><h4>지원내용</h4><p>고위험 임산부 입원치료비의 90% 지원 ※ 상급병실입원료 및 환자 특식 제외</p><p>1인당 300만원 한도</p></div>')
        result=structured_brief('고위험 임산부 의료비는 얼마나 지원받을 수 있나요?',doc('고위험 임산부 의료비지원'),body,{'고위험임산부','의료비'})
        self.assertIn('90%',result['answer'])
        self.assertIn('300만원 한도',result['answer'])
        self.assertIn('환자 특식 제외',result['answer'])
        self.assertNotIn('**질환기준**',result['answer'])

    def test_support_heading_preserves_nested_amount_label(self):
        body=official_html_text('<div id="conts"><h3>청소년부모가정지원</h3><h4>배경</h4><p>양육 부담 경감을 위함</p><h4>대상</h4><p>대상: 부모 모두 24세 이하, 중위소득 65% 이하</p><h4>지원내용</h4><p>아동양육비 : 자녀 1명당 월 25만원</p></div>')
        result=structured_brief('청소년부모 가정은 어떤 지원을 받을 수 있나요?',doc('가족'),body,{'청소년','가정'})
        self.assertIn('25만원',result['answer'])
        self.assertIn('65% 이하',result['answer'])
        self.assertNotIn('**배경**',result['answer'])

    def test_all_required_eligibility_rows_remain_with_intro(self):
        body=official_html_text('<div id="conts"><h3>응시료 지원</h3><h4>지원대상</h4><p>18세~39세 중 아래 요건을 모두 충족하는 자</p><p>- 거주기준: 사하구 1년 이상 계속 거주자</p><p>- 근로이력: 미취업자 및 사업자등록사실이 없는 자</p><h4>지원내용</h4><p>연 1회 응시료 지원</p></div>')
        result=structured_brief('응시료 지원을 받을 수 있나요?',doc('응시료 지원'),body,{'응시료'})
        self.assertIn('1년 이상',result['answer'])
        self.assertIn('사업자등록사실이 없는',result['answer'])

    def test_online_certificate_keeps_method_and_normal_result_condition(self):
        body=official_html_text('<div id="conts"><h3>제증명온라인발급</h3><p>발급 민원: 건강진단결과서(검사 결과 정상일 경우에만 온라인 발급 가능)</p><p>온라인 발급: 공공보건포털 https://www.e-health.go.kr</p><h4>공공보건포털 이용시 유의사항</h4><p>건강진단결과서는 검사일로부터 1년간만 발급 가능합니다.</p></div>')
        result=structured_brief('보건증을 보건소에 다시 가지 않고 온라인으로 발급받을 수 있나요?',doc('제증명'),body,{'건강진단결과서','인터넷'})
        self.assertIn('정상일 경우',result['answer'])
        self.assertIn('https://www.e-health.go.kr',result['answer'])
        self.assertIn('1년간',result['answer'])

    def test_factual_h_tag_keeps_clinic_scope_and_usage_conditions(self):
        body=official_html_text('<div id="conts"><h3>금연클리닉 운영</h3><h4>흡연자를 대상으로 금연 상담 및 보조제 지원 등을 통해 금연 실천율을 높이고 건강한 삶을 살아갈 수 있도록 함</h4><p>기간: 월~금 09:00~18:00, 청소년은 예약 필수</p><p>대상: 금연을 희망하는 지역주민</p><p>장소: 보건소 2층 금연클리닉</p><h4>금연클리닉 대상자 등록 후 6개월간 서비스 제공</h4><h3>이동 금연 클리닉</h3><p>대상: 10명 이상 사업장</p></div>')
        result=structured_brief('금연클리닉은 누가 이용하나요?',doc('금연'),body,{'금연','클리닉'})
        self.assertIn('보조제',result['answer'])
        self.assertIn('예약 필수',result['answer'])
        self.assertIn('2층',result['answer'])
        self.assertNotIn('10명 이상',result['answer'])

    def test_publication_question_does_not_select_appeal_period(self):
        body=official_html_text('<div id="conts"><h3>개별(공동)주택가격안내</h3><h4>개별(공동)주택의 결정·공시일은?</h4><p>1월 1일 기준: 매년 4월말</p><p>6월 1일 기준: 매년 9월말</p><h4>개별(공동)주택가격 이의신청기간은?</h4><p>1월 1일 기준: 공시일로부터 30일간</p></div>')
        result=structured_brief('개별주택가격과 공동주택가격은 언제 공시되나요?',doc('주택가격'),body,{'주택','가격','공시','개별','공동'})
        self.assertIn('4월말',result['answer'])
        self.assertIn('9월말',result['answer'])
        self.assertNotIn('30일',result['answer'])

    def test_automatic_insurance_registration_answers_necessity(self):
        body=official_html_text('<div id="conts"><h3>구민안전보험</h3><p>가입절차: 모든 구민 자동가입(전입 시 자동가입, 전출 시 자동해지)</p><p>보험기간: 2026년</p><p>보장금액: 500만원</p></div>')
        result=structured_brief('구민안전보험에 따로 가입해야 하나요?',doc('보험'),body,{'구민','안전','보험','가입'})
        self.assertIn('자동가입',result['answer'])
        self.assertNotIn('500만원',result['answer'])

    def test_spaced_target_and_participation_condition_are_fields(self):
        from chatbot.structured_answers import field_matches
        self.assertTrue(field_matches('eligibility','지원 대상: 첫째아이 임신 준비 중 신혼부부 및 결혼 예정 사하구민'))
        self.assertTrue(field_matches('eligibility','참여조건: 고유번호가 있는 계량기 부착'))

    def test_request_format_and_symptom_do_not_erase_service_subject(self):
        from chatbot.query_subject import query_keywords
        self.assertIn('검사비용',query_keywords('보건소 각종 검사 비용은 어디에서 확인하나요?',{'보건소','각종','검사','비용'}))
        topics=query_keywords('우울감이나 정신건강 문제를 상담받을 곳',{'우울감','정신건강','문제','상담'})
        self.assertEqual(topics,{'정신건강'})

    def test_statutory_classes_establish_legal_infection_topic(self):
        from chatbot.evidence import topic_support
        self.assertTrue(topic_support({'content':'제1급감염병: 에볼라바이러스병\n제2급감염병: 결핵'},{'법정감염병'})[0])
        self.assertFalse(topic_support({'content':'감기와 일반 감염병 안내'},{'법정감염병'})[0])

    def test_facility_rows_filter_selected_dong(self):
        body='## 민방위 시설\n1 — 동명: 괴정동 · 위치: 괴정로 1\n2 — 동명: 당리동 · 위치: 제석로 2'
        result=structured_brief('당리동 민방위 시설은 어디에 있나요?',doc('민방위 시설'),body,{'민방위'})
        self.assertIn('제석로 2',result['answer'])
        self.assertNotIn('괴정로',result['answer'])

    def test_missing_area_cannot_fall_back_to_first_facility_row(self):
        body='## 민방위 시설\n1 — 동명: 괴정동 · 위치: 괴정로 1\n2 — 동명: 당리동 · 위치: 제석로 2'
        result=structured_brief('감천동 민방위 시설 어디에 있나요?',doc('민방위 시설'),body,{'민방위'})
        self.assertTrue(result['is_clarification'])
        self.assertNotIn('괴정로',result['answer'])
        self.assertNotIn('제석로',result['answer'])

    def test_html_column_missing_retries_only_the_legacy_fields(self):
        from database_db.raw_pages import read_raw_pages
        from types import SimpleNamespace
        selected=[]
        class Query:
            def select(self,fields): selected.append(fields); self.fields=fields; return self
            def eq(self,*_):return self
            def limit(self,*_):return self
            def execute(self):
                if 'raw_html' in self.fields:raise RuntimeError('column raw_pages.raw_html does not exist')
                return SimpleNamespace(data=[{'content':'기존 본문'}])
        result=read_raw_pages(SimpleNamespace(table=lambda _:Query()),'content,raw_html',url='official',limit=1)
        self.assertEqual(result,[{'content':'기존 본문'}]);self.assertEqual(selected,['content,raw_html','content'])

    def test_network_error_is_not_retried_as_a_schema_problem(self):
        from database_db.raw_pages import read_raw_pages
        from types import SimpleNamespace
        class Query:
            def select(self,_):return self
            def execute(self):raise RuntimeError('Network unavailable')
        with self.assertRaisesRegex(RuntimeError,'Network'):
            read_raw_pages(SimpleNamespace(table=lambda _:Query()),'content,raw_html')

    def test_certificate_availability_answers_service_instead_of_authentication(self):
        body=official_html_text('<div id="conts"><h3>정부24</h3><p>정부24는 민원을 인터넷으로 신청·열람·발급할 수 있는 정부서비스입니다.</p><h4>정부24 민원서비스</h4><p>민원 발급 안내</p><h4>이용방법</h4><p>회원가입 후 인증서를 이용합니다.</p></div>')
        result=structured_brief('정부24로 구청에 가지 않고 민원서류를 발급받을 수 있나요?',doc('정부24'),body,{'정부24'})
        self.assertIn('신청·열람·발급',result['answer'])

    def test_tax_eligibility_recognizes_the_taxpayer_label(self):
        body=official_html_text('<div id="conts"><h3>자동차세</h3><p>납세의무자: 자동차를 소유하는 자</p><p>과세표준: 1000cc</p></div>')
        result=structured_brief('자동차세는 누가 내나요?',doc('지방세종류'),body,{'자동차세'})
        self.assertIn('소유하는 자',result['answer'])
        self.assertNotIn('1000cc',result['answer'])

    def test_question_heading_is_not_a_fact_and_definition_is_labelled(self):
        body=official_html_text('<div id="conts"><h3>민간임대 등록제도란?</h3><p>개인이나 법인이 임대사업자로 등록하는 제도</p></div>')
        self.assertIn('### 민간임대 등록제도란?',body)
        self.assertIn('정의: 개인이나 법인이',body)

    def test_definition_does_not_select_application_consent_document(self):
        from chatbot.structured_answers import field_matches
        self.assertFalse(field_matches('definition','구비서류: 공공근로사업신청서 및 개인정보제공동의서'))

    def test_service_title_owns_all_of_its_fields(self):
        body=official_html_text('<div id="conts"><h3>영양플러스</h3><h4>신청기준</h4><p>거주기준: 사하구민</p><p>영양기준: 영양위험요인 보유자</p><p>소득기준: 중위소득 기준 이하</p><h4>지원내용</h4><p>영양상담 제공</p></div>')
        result=structured_brief('영양플러스 대상은 누구인가요?',doc('영양플러스'),body,{'영양플러스'})
        self.assertIn('거주기준',result['answer']);self.assertIn('영양위험요인',result['answer']);self.assertIn('소득기준',result['answer'])

    def test_a_table_wrapper_is_not_duplicated_as_flat_prose(self):
        body=official_html_text('<div id="conts"><h3>지원</h3><li>가격<table><tr><th>대상</th><td>12세 이하</td></tr></table></li></div>')
        self.assertEqual(body.count('12세 이하'),1)

    def test_fee_question_does_not_scope_to_short_parking_definition(self):
        from chatbot.concise_answers import topic_section_bounds
        units=['## 불법주정차 단속 안내','### 정차','정차: 5분 이하','### 과태료 감경','감경내용: 자진납부시 20% 감경']
        bounds=topic_section_bounds(units,'불법주정차 과태료 자진납부 감경',{'주정차','과태료','자진납부','감경'})
        self.assertNotEqual(bounds,(1,3))

    def test_missing_clear_html_field_is_not_a_redundant_clarification(self):
        from chatbot.concise_answers import concise_source_answer
        body='## 상담실\n위치: 사하구청 민원실'
        result=concise_source_answer('상담실 여는시간','\n'.join('> '+l for l in body.splitlines()),[doc('상담실')],{'상담실'})
        self.assertFalse(result['is_clarification']);self.assertTrue(result['degraded'])

    def test_reviewed_dates_are_quarantined_until_the_page_changes(self):
        from chatbot.source_warnings import reviewed_source
        meta={'url':'https://www.saha.go.kr/portal/contents.do?mId=0404010100'}
        text='정의: 개별토지의 단위면적당 가격\n1.1일 기준 : 5월 말'
        body,updated=reviewed_source(text,meta)
        self.assertNotIn('5월',body);self.assertIn('schedule',updated['unverified_fields'])
        body,updated=reviewed_source(text.replace('5월','4월'),meta)
        self.assertNotIn('unverified_fields',updated)

    def test_old_invitation_warning_excludes_historical_reference_dates(self):
        from chatbot.source_warnings import dated_invitation_warning
        self.assertTrue(dated_invitation_warning('2025년 사업을 실시하니 많은 참여 바랍니다.',year=2026))
        self.assertFalse(dated_invitation_warning('1995년 1월부터 실시하고 있는 제도입니다.',year=2026))

    def test_age_range_stays_in_its_own_program_row(self):
        html = '<div id="conts"><h3>돌봄 안내</h3><table><tr><th>구분</th><th>대상</th><th>내용</th></tr><tr><th>아이돌봄 지원사업</th><td>생후 3개월 이상<br>~<br>12세 이하 아동</td><td>돌봄 서비스 제공</td></tr><tr><th>어린이집</th><td>6세 미만</td><td>보육</td></tr></table></div>'
        body = official_html_text(html)
        result = structured_brief('아이돌봄은 몇 살까지 이용하나요?',doc('아동복지'),body,{'아이돌봄'})
        self.assertIn('3개월 이상 ~ 12세 이하',result['answer'])
        self.assertNotIn('6세 미만',result['answer'])

    def test_disability_pension_preserves_both_conditions(self):
        body = official_html_text('<div id="conts"><h4>장애인 연금</h4><h5>지원대상</h5><ul><li>장애인연금법상 중증장애인에 해당하는 자</li><li>본인과 배우자의 소득인정액이 선정 기준액 이하인 자</li></ul><h4>장애아동수당</h4><p>대상: 18세 미만 아동</p></div>')
        result=structured_brief('장애인연금은 누가 신청하나요?',doc('제도시책'),body,{'장애인연금'})
        self.assertIn('중증장애인',result['answer'])
        self.assertIn('소득인정액',result['answer'])
        self.assertNotIn('18세 미만',result['answer'])

    def test_job_seeker_does_not_select_employer_registration(self):
        body=official_html_text('<div id="conts"><h3>이용안내</h3><h4>구인안내</h4><p>절차: 구인표 작성 후 채용담당자 등록</p><h4>구직정보</h4><p>방법: 본인 내방등록</p><p>지참물: 신분증</p><p>절차: 구직표 작성 후 구직등록</p><h4>구직필증</h4><p>절차: 구직필증발급</p></div>')
        result=structured_brief('구직 등록은 어떻게 하나요?',doc('구인 구직'),body,{'구직'})
        self.assertIn('본인 내방등록',result['answer'])
        self.assertIn('신분증',result['answer'])
        self.assertNotIn('구인표',result['answer'])
        self.assertNotIn('구직필증발급',result['answer'])

    def test_repeated_fields_in_different_services_are_preserved(self):
        body=official_html_text('<div id="conts"><h4>법인지방소득세</h4><p>방법: 위택스 인터넷 신고</p><h4>주민세 신고</h4><p>방법: 위택스 인터넷 신고</p></div>')
        self.assertEqual(body.count('방법: 위택스 인터넷 신고'),2)
        units=_source_units(body.splitlines());bounds=named_section_bounds(units,'주민세 신고 방법')
        self.assertIn('방법: 위택스 인터넷 신고',units[bounds[0]:bounds[1]])

    def test_row_span_prices_keep_the_same_owner(self):
        body=official_html_text('<div id="conts"><h3>수수료</h3><table><tr><th>품목</th><th>규격</th><th>가격</th></tr><tr><th rowspan="2">일반침대</th><td>1인용</td><td>10000원</td></tr><tr><td>2인용</td><td>15000원</td></tr></table></div>')
        self.assertIn('일반침대 — 가격: 15000원',body)
        self.assertNotIn('2인용 — 가격',body)

    def test_vertical_th_cells_are_labels_not_column_headers(self):
        body=official_html_text('<div id="conts"><table><tr><th>기간</th><th>연중</th></tr><tr><th>진료대상</th><td>검진을 원하는 자</td></tr></table></div>')
        self.assertIn('기간: 연중',body)
        self.assertIn('진료대상: 검진을 원하는 자',body)
        self.assertNotIn('연중:',body)

    def test_embedded_board_does_not_hide_real_tb_service(self):
        d=doc();d['content']='진료대상: 결핵검진을 원하는 자\n진료내용: 흉부검사\n게시판 목록 작성일 조회 검색어를 입력'
        self.assertTrue(is_answerable_document('결핵 검사 가능한가요?',d))
        d['metadata']['url']='https://www.saha.go.kr/health/bbs/list.do?mId=test'
        self.assertFalse(is_answerable_document('결핵 검사 가능한가요?',d))

    def test_html_notice_table_is_excluded(self):
        body=official_html_text('<div id="conts"><h3>진료안내</h3><p>진료내용: 흉부 검사</p><table class="tableSt_list"><tr><td>공지사항 작성일 조회</td></tr></table></div>')
        self.assertNotIn('작성일',body)

    def test_bicycle_rental_cannot_use_waste_free_pickup(self):
        d=doc('대형폐기물');d['content']='자전거: 배출수수료 3000원. 폐가전 무상수거.'
        self.assertFalse(is_service_source('자전거 무료로 빌릴 곳 있나요?',d,{'자전거','무상'}))

    def test_heading_is_not_a_model_fact(self):
        p={'units':['### 지원내용','지원내용: 90% 지원'], 'document':doc()}
        self.assertNotIn(0,eligible_ids('지원금액 얼마인가요?',p,{'지원'}))

    def test_official_numeric_url_identifiers_survive_output_mask(self):
        for url in ['https://www.saha.go.kr/portal/contents.do?mId=0103020000','https://www.saha.go.kr/cmm/fms/FileDown.do?atchFileId=FILE_000000001234567&fileSn=0']:
            self.assertEqual(mask_answer('[공식 원문]('+url+')')[0],'[공식 원문]('+url+')')
        self.assertIn('[MASKED:전화번호]',mask_answer('휴대폰 01012345678')[0])
        self.assertIsNotNone(detect_personal_info('01012345678',use_ner=False))

    def test_url_cannot_hide_pii_in_unrecognized_query_param(self):
        value='https://www.saha.go.kr/portal/contents.do?phone=01012345678'
        self.assertIn('[MASKED:전화번호]',mask_answer(value)[0])
        value='https://saha.go.kr.evil.example/?mId=01012345678'
        self.assertIn('[MASKED:전화번호]',mask_answer(value)[0])

    def test_compound_target_and_documents_keeps_both_fields(self):
        body=official_html_text('<div id="conts"><h3>임산부 등록</h3><p>대상: 사하구에 거주하는 임산부</p><p>준비물: 신분증, 예정일이 기재된 임신확인서</p><h3>임신 초기검사</h3><p>대상: 12주 미만 임산부</p></div>')
        result=structured_brief('임산부 등록은 누가 하고 무엇을 가져가나요?',doc('임산부 관리'),body,{'임산부등록'})
        self.assertIn('예정일',result['answer']);self.assertNotIn('12주 미만',result['answer'])
