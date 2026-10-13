import unittest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from chatbot.privacy import detect_personal_info
from chatbot.emergency_guidance import answer_emergency_question


class SafetyGeneralizationTests(unittest.TestCase):
    def test_age_and_duration_are_not_private_addresses(self):
        for q in ('장애인연금을 받고 있으면 65세가 되어도 그대로 받나요?',
                  '다대포 축구장을 빌리면 2시간 사용료가 얼마예요?',
                  '지원 조건이 맞으면 10만원 받을 수 있나요?'):
            self.assertIsNone(detect_personal_info(q, use_ner=False), q)

    def test_private_street_lot_and_mobile_numbers_still_block(self):
        for q in ('당리동 123-45에 살아요', '낙동대로 398번길 12에서 신청',
                  '제 번호는 010-1234-5678입니다'):
            self.assertIsNotNone(detect_personal_info(q, use_ner=False), q)

    def test_smoke_at_a_factory_gets_immediate_emergency_guidance(self):
        answer = answer_emergency_question('공장에서 연기가 나는데 당리동이면 구청에 먼저 신고해요?')
        self.assertIn('119', answer['answer'])
        self.assertIn('대피', answer['answer'])

    def test_schedule_postponement_is_not_a_fire(self):
        for q in ('공장 안전교육 일정이 연기됐나요?', '금연 교육 신청 방법', '공장 화재 보험 보상'):
            self.assertIsNone(answer_emergency_question(q))


class GeneralSourceTests(unittest.TestCase):
    def test_active_headings_do_not_inherit_previous_sibling_service(self):
        from chatbot.source_hierarchy import heading_path
        path=heading_path(['## 검사안내','### A형간염','비용: 10,000원','### B형간염','비용: 8,000원'],4)
        self.assertIn('B형간염',path)
        self.assertNotIn('A형간염',path)

    def test_all_requirements_survive_intermediate_field_headings(self):
        from chatbot.concise_answers import _source_units,condition_indices
        body='## 응시료 지원\n### 지원대상\n지원대상: 18~39세 청년 중 아래 요건을 모두 충족하는 자\n#### 거주기준\n거주기준: 신청일 기준 1년 이상 거주자\n#### 근로이력\n근로이력: 미취업자 및 사업자등록사실이 없는 자'
        units=_source_units(body.splitlines());index=next(i for i,u in enumerate(units) if u.startswith('지원대상:'))
        selected='\n'.join(units[i] for i in condition_indices(units,[index]))
        self.assertIn('1년 이상',selected)
        self.assertIn('사업자등록사실이 없는 자',selected)

    def test_national_telephone_program_does_not_enrich_local_clinic(self):
        from chatbot.concise_answers import _source_units,topic_section_bounds
        body='## 금연\n### 금연클리닉 운영\n대상: 금연을 희망하는 지역주민\n내용: 6개월 상담과 보조제 지원\n##### 국가 금연상담전화 안내\n내용: 30일 상담 프로그램 제공'
        units=_source_units(body.splitlines());bounds=topic_section_bounds(units,'금연클리닉 대상',{'금연','클리닉'})
        scoped='\n'.join(units[bounds[0]:bounds[1]])
        self.assertIn('6개월',scoped)
        self.assertNotIn('30일',scoped)
    def test_official_numbered_formula_remains_complete(self):
        from chatbot.answer_completion import balanced,source_unit_complete
        formula='2. 임대차의 경우 거래금액 계산 1) 거래금액 = 보증금 + (월차임 x 100) 2) 5천만원 미만이면 거래금액 = 보증금+(월차임 x 70)'
        self.assertTrue(balanced(formula))
        self.assertTrue(source_unit_complete(formula))
        self.assertFalse(balanced('사진 크기 (3.5 x 4.5'))
        self.assertFalse(balanced('사진 크기 3.5cm) 확인'))
    def test_table_item_size_and_total_are_not_detached(self):
        from chatbot.official_content import official_html_text
        from chatbot.structured_answers import structured_brief
        body=official_html_text('<div id="conts"><h3>대형폐기물</h3><table><tr><th>구분</th><th>품명</th><th>규격</th><th>수수료 / 계</th><th>수집운반비</th></tr><tr><td>가구</td><td>소파</td><td>2인용</td><td>9,000원</td><td>5,000원</td></tr><tr><td>가구</td><td>소파</td><td>3인용</td><td>13,000원</td><td>8,000원</td></tr></table></div>')
        result=structured_brief('대형폐기물 2인용 소파 비용 얼마야?',{'metadata':{'title':'대형폐기물'}},body,{'대형폐기물'})
        self.assertIn('9,000원',result['answer'])
        self.assertNotIn('13,000원',result['answer'])
        self.assertNotIn('5,000원',result['answer'])

    def test_bundled_panel_cannot_establish_standalone_test_price(self):
        from chatbot.source_scope import focus_units
        units=['산전검사 [B형간염, 에이즈, 혈액형] — 수수료: 41,210원',
               '에이즈검사 — 수수료: 무료']
        selected=focus_units('에이즈 검사 비용',units)
        self.assertEqual(selected,['에이즈검사 — 수수료: 무료'])

    def test_provider_checkbox_does_not_remove_cancer_age_and_period(self):
        from chatbot.structured_answers import structured_brief
        body='## 국가암검진사업\n### 검진항목\n위암 — 대상자: 만40세 이상\n위암 — 검진주기: 2년\n대장암 — 대상자: 만50세 이상\n### 국가암검진 의료기관\n기관1 — 암검진 / 위암: ○'
        result=structured_brief('국가암검진 위암 몇 살부터 몇 년마다?',{'metadata':{'title':'국가암검진사업'}},body,{'국가암검진'})
        self.assertIn('40세',result['answer'])
        self.assertIn('2년',result['answer'])
        self.assertNotIn('50세',result['answer'])
        self.assertNotIn('기관1',result['answer'])

    def test_all_people_condition_uses_actual_target_row_instead_of_provider_note(self):
        from chatbot.structured_answers import structured_brief
        body='## 국가암검진사업\n### 검진항목\n폐암 — 대상자: 만54~74세 중 30갑년 이상 흡연력을 가진 자\n### 국가암검진 의료기관\n※ 검진기관 방문시 전화 예약 필요'
        result=structured_brief('폐암검진은 모든 50대가 무료로 받나요?',{'metadata':{'title':'국가암검진사업'}},body,{'국가암검진'})
        self.assertIn('54~74세',result['answer'])
        self.assertNotIn('전화 예약',result['answer'])

    def test_processing_time_is_not_opening_hours(self):
        from chatbot.structured_answers import field_matches
        q='여권 신청하면 당일 나와요?'
        self.assertFalse(field_matches('schedule','근무시간: 평일 09:00~18:00',q))
        self.assertTrue(field_matches('schedule','여권교부: 근무일 기준 8~10일 소요',q))

    def test_short_certificate_reply_preserves_exemption_profile(self):
        from chatbot.response_helpers import resolve_clarification_reply
        query = resolve_clarification_reply('주민등록등본이요.', {
            'query':'기초생활수급자인데 발급비 면제돼요?', 'reply_terms':['등본','초본','인감']})
        self.assertIn('기초생활수급자',query)
        self.assertIn('주민등록등본',query)

    def test_missing_location_does_not_erase_available_registration_documents(self):
        from chatbot.structured_answers import structured_brief
        body='## 임산부건강관리\n### 임산부 등록\n대상: 사하구 거주 임산부\n준비물: 신분증, 분만예정일이 적힌 임신확인서 또는 임산부 수첩'
        result=structured_brief('임산부 등록 가져갈 서류랑 등록 장소가 궁금해요.',
            {'metadata':{'title':'임산부건강관리'}},body,{'임산부등록'})
        self.assertIn('임신확인서',result['answer'])
        self.assertIn('장소 정보는 이 자료에서 명확히 확인되지',result['answer'])
        self.assertTrue(result['degraded'])

    def test_audience_comparison_keeps_cutoff_and_does_not_choose_other_column(self):
        from chatbot.structured_answers import structured_brief
        body='## 암환자 의료비지원\n### 암환자 의료비지원\n사업목적: 암환자 치료비 지원\n### 지원대상 및 내용\n선정기준 — 건강보험가입자: 2021년 6월 30일까지 진단받고 보험료 기준을 충족한 자\n선정기준 — 의료급여수급자: 당연선정\n지원금액 — 의료급여수급자: 300만원\n### 서류안내\n신청서류: 진단서 및 신분증 제출'
        result=structured_brief('암 치료비 신청 건강보험 가입자예요.',
            {'metadata':{'title':'암환자 의료비지원'}},body,{'암환자','의료비'})
        self.assertIn('2021년 6월 30일',result['answer'])
        self.assertNotIn('당연선정',result['answer'])
        self.assertNotIn('300만원',result['answer'])

    def test_snapshot_search_reads_actual_html_table_and_avoids_reparse(self):
        from unittest.mock import Mock, patch
        from chatbot.crawled_pages import CrawledPageIndex
        from chatbot.official_content import official_html_text
        html='<div id="conts"><h3>유료 성인예방접종</h3><table><tr><th>종류</th><th>횟수</th><th>수수료</th></tr><tr><td>B형 간염</td><td>3회</td><td>8,000원</td></tr></table></div>'
        row={'url':'https://www.saha.go.kr/health/contents.do?mId=0203020000','title':'성인예방접종','content':'B형 간염 3회 8,000원','raw_html':html,'last_checked_at':datetime.now(timezone.utc).isoformat()}
        index=CrawledPageIndex(Mock())
        with patch('database_db.raw_pages.read_raw_pages',return_value=[row]), patch('chatbot.official_content.official_html_text',wraps=official_html_text) as parse:
            index._load_pages()
            for _ in range(2):
                results=index.search('B형간염 접종 비용',{'b형간염'})
                self.assertEqual(len(results),1)
                self.assertIn('B형 간염 — 수수료: 8,000원',results[0]['content'])
            self.assertEqual(sum(bool(c.args[0]) for c in parse.call_args_list),1)

    def test_failed_initial_snapshot_retries_without_caching_empty_result(self):
        from unittest.mock import Mock, patch
        from chatbot.crawled_pages import CrawledPageIndex
        index = CrawledPageIndex(Mock())
        row = {'url':'official','content':'원문'}
        with patch('database_db.raw_pages.read_raw_pages',side_effect=[TimeoutError(),[row]]) as read:
            index._load_pages()
            self.assertIsNone(index._loaded_at)
            self.assertEqual(index._snapshot(), [])
            self.assertEqual(read.call_count, 1)
            index._retry_at = 0
            self.assertEqual(index._snapshot(), [row])
            self.assertEqual(read.call_count, 2)
            self.assertEqual(read.call_args.kwargs['count'], 25)

    def test_bulleted_all_requirements_survive_model_selection(self):
        from chatbot.concise_answers import condition_indices
        units = ['### 응시료 지원', '#### 지원대상',
                 '지원대상: 18세~39세 중 아래 요건을 모두 충족하는 자',
                 '- 거주기준: 신청일 기준 1년 이상 계속 거주자',
                 '- 근로이력: 미취업자 및 사업자등록사실이 없는 자',
                 '#### 지원내용', '지원내용: 연 1회 지원']
        self.assertEqual(condition_indices(units,[2]),[2,3,4])

    def test_requested_detail_precedes_another_programs_field_coverage(self):
        from chatbot.structured_answers import structured_brief
        body = ('## 임산부건강관리\n### 철분제 지원\n대상: 사하구 거주 임산부\n'
                '지원내용: 임신 16주부터 최대 5개월분 지원\n### 장애인 임산부 지원\n'
                '대상: 임신부터 분만 후 6개월까지 여성장애인\n내용: 건강상담 지원')
        result = structured_brief('임산부 철분제는 몇 주부터 얼마나 받을 수 있어요?',
            {'metadata':{'title':'임산부건강관리'}},body,{'임산부'})
        self.assertIn('16주',result['answer'])
        self.assertNotIn('여성장애인',result['answer'])

    def test_source_definition_without_question_mark_and_income_comparison(self):
        from chatbot.official_content import official_html_text
        from chatbot.structured_answers import structured_brief
        body = official_html_text('<div id="conts"><h3>마을기업 이란</h3><p>지역 자원을 활용하여 공동체 이익을 실현하는 기업</p></div>')
        self.assertIn('정의: 지역 자원',body)
        body = ('## 급여 기준\n생계급여 (중위 32%) — 1인: 100원\n'
                '의료급여 (중위 40%) — 1인: 200원')
        result = structured_brief('생계급여랑 의료급여의 소득 기준이 같아요?',
            {'metadata':{'title':'급여 기준'}},body,{'생계급여','의료급여'})
        self.assertIn('32%',result['answer'])
        self.assertIn('40%',result['answer'])
        self.assertNotIn('100원',result['answer'])

    def test_method_fallback_never_uses_marketing_or_phone_as_procedure(self):
        from chatbot.concise_answers import _extract_brief
        body = ['## 자격증 응시료 지원',
                '많은 신청 바랍니다.',
                '지원대상: 18세~39세 청년 중 아래 요건을 모두 충족하는 자',
                '- 거주기준: 신청일 기준 1년 이상 계속 거주자',
                '신청방법: 홈페이지에서 신청서 작성 및 서류 업로드']
        answer = _extract_brief('응시료 지원 신청 방법',body,{'응시료'},'응시료 지원')
        self.assertIn('신청서 작성',answer)
        self.assertNotIn('많은 신청',answer)
        self.assertIsNone(_extract_brief('형광등 어디에 버려야 해?',
            ['## 폐기물','폐형광등 배출 안내','수거업체 — 전화번호: 051-000-0000'],{'형광등'},'폐기물'))

    def test_age_transition_is_not_answered_with_general_eligibility(self):
        from chatbot.structured_answers import field_matches
        q = '장애인연금은 65세가 되어도 그대로 받아요?'
        self.assertFalse(field_matches('conditions','지원대상: 중증장애인 중 소득인정액 기준 이하인 자',q))
        self.assertTrue(field_matches('conditions','지원대상: 65세 이상은 기초급여 제외',q))
        from chatbot.grounded_planner import matches_field
        self.assertFalse(matches_field(q,'conditions','지원대상: 중증장애인 중 소득인정액 기준 이하인 자'))

    def test_named_program_audience_does_not_require_repeating_generic_patient_name(self):
        from chatbot.concise_answers import _extract_brief
        body = ['## 영양플러스', '임산부 및 영유아 지원 안내',
                '연령기준: 만 6세 이하 영유아, 임신부, 출산부 및 수유부',
                '소득기준: 중위소득 80% 이하']
        answer = _extract_brief('영양플러스는 임산부만 대상인가요?',body,
                                {'영양플러스','임산부'},'영양플러스')
        self.assertIn('영유아',answer)
        self.assertIn('소득기준',answer)
        self.assertNotIn('정확히 안내할',answer)

    def test_regular_tax_period_excludes_optional_annual_payment(self):
        from chatbot.structured_answers import structured_brief
        body='## 자동차세\n### 납기\n납기: 제1기분 6월 16일~6월 30일\n납기: 제2기분 12월 16일~12월 31일\n### 연납\n1월 — 연납세액신고 및 납부기간: 1월 16일~1월 31일'
        result=structured_brief('자동차세 보통 몇 월에 내요?',{'metadata':{'title':'자동차세'}},body,{'자동차세'})
        self.assertIn('6월',result['answer'])
        self.assertIn('12월',result['answer'])
        self.assertNotIn('1월',result['answer'])

    def test_area_selects_own_program_and_frequency(self):
        from chatbot.official_content import official_html_text
        from chatbot.structured_answers import structured_brief
        body=official_html_text('<div id="conts"><h3>1인가구 지원</h3><table><tr><th>구분</th><th>사업명</th><th>사업내용</th><th>지역</th></tr><tr><td>돌봄</td><td>반찬 나눔</td><td>주 1회 반찬 제공</td><td>괴정2동</td></tr><tr><td>돌봄</td><td>사랑 반찬</td><td>월 2회 반찬 제공</td><td>괴정3동</td></tr></table></div>')
        result=structured_brief('괴정2동 1인가구 반찬 주기는?',{'metadata':{'title':'1인가구 지원'}},body,{'1인가구'})
        self.assertIn('주 1회',result['answer'])
        self.assertNotIn('월 2회',result['answer'])

    def test_incidental_service_mention_does_not_become_its_guide(self):
        from chatbot.evidence import is_service_source
        self.assertFalse(is_service_source('암환자 치료비 신청',{
            'content':'## 방문건강관리\n대상: 암환자 등 취약계층\n내용: 방문 상담',
            'metadata':{'title':'방문건강관리'}},{'암환자'}))

    def test_missing_detail_cannot_fall_back_to_service_introduction(self):
        from chatbot.source_answers import build_source_answer
        doc={'content':'여권은 여행자 신분을 증명하는 공문서입니다.',
             'metadata':{'title':'여권','source_type':'crawled_page','url':'https://www.saha.go.kr/portal/contents.do?mId=0104010000'}}
        answer,used=build_source_answer([doc],None,query='여권 이름에 하이픈을 넣어도 돼요?',topic_keywords={'여권'})
        self.assertEqual((answer,used),('',[]))

    def test_contact_clarification_keeps_reporting_intent(self):
        from chatbot.response_helpers import build_contextual_search_query
        history=[{'role':'user','content':'신고 전화번호 알려줘'},
                 {'role':'assistant','content':'문의할 업무나 부서명을 알려주세요.'}]
        q=build_contextual_search_query('식당 위생 때문에 신고하려고 해요.',history)
        self.assertIn('전화번호',q)
        self.assertIn('식당',q)

    def test_long_condition_reply_preserves_program_but_new_topic_is_separate(self):
        from chatbot.response_helpers import resolve_clarification_reply
        pending={'query':'암 치료비 지원 신청','reply_terms':['건강보험']}
        q=resolve_clarification_reply('저는 의료급여가 아니고 건강보험 가입자인데 신청 가능한지 궁금해요',pending)
        self.assertIn('암 치료비',q)
        self.assertEqual(resolve_clarification_reply('여권 사진 몇 장이에요?',pending),'여권 사진 몇 장이에요?')


class GeneralContactTests(unittest.TestCase):
    def test_inspection_and_health_organization_scope(self):
        from chatbot.contact_directory import ContactDirectoryResponder
        now=datetime.now(timezone.utc).isoformat()
        def row(phone,duties,keywords):
            return {'title':'주무관','phone':phone,'duties':duties,'keywords':keywords}
        data={'schema_version':1,'staff_checked_at':now,'representative_checked_at':now,
              'staff_source_url':'https://www.saha.go.kr/portal/staff/list.do',
              'departments':[
                  {'name':'위생과','contacts':[row('051-220-9991','음식점 보험 관리',['음식점','위생']),row('051-220-9992','식품,공중위생업소 지도점검 및 행정처분',['식품','위생'])]},
                  {'name':'보건소','contacts':[row('051-220-9993','보건소 업무총괄',['총괄'])]},
                  {'name':'건강증진과','contacts':[row('051-220-9994','임산부 건강관리사업',['임산부'])]},
                  {'name':'경제진흥과','contacts':[row('051-220-9995','임산부 농산물 지원',['임산부'])]},
                  {'name':'자원순환과','contacts':[row('051-220-9996','대형폐기물 관련 업무',['대형폐기물','폐기물배출'])]}]}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'contacts.json';path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            responder=ContactDirectoryResponder(path)
            self.assertIn('9992',responder.respond('x','식당 위생 상태 신고 담당 전화번호')['answer'])
            self.assertNotIn('9991',responder.respond('x','식당 위생 상태 신고 담당 전화번호')['answer'])
            self.assertIn('9994',responder.respond('y','임산부 지원사업 문의하는 보건소 번호')['answer'])
            self.assertIn('9996',responder.respond('z','대형폐기물 배출 문의 담당 전화번호')['answer'])


class ReportFactsTests(unittest.TestCase):
    def report(self,body,period='2023-01-01~2025-12-31'):
        return {'content':body,'metadata':{'url':'file://official_reports/example/page-3',
            'source_type':'official_report','source_title':'정보공개청구 분석보고서',
            'title':'정보공개청구 분석보고서 (3쪽)','data_period':period,'page_number':3,'issued_at':'2026-08-04'}}

    def test_count_uses_requested_year_and_column(self):
        from chatbot.official_reports import report_answer
        result=report_answer('정보공개청구 보고서에서 2025년 청구 건수는 몇 건인가요?',[
            self.report('2024년 — 청구: 2,216\n2025년 — 청구: 1,965\n2025년 — 처리: 1,963')])
        self.assertIn('1,965',result['answer'])
        self.assertNotIn('1,963',result['answer'])
        self.assertIn('2025년',result['answer'])

    def test_current_and_conflicting_counts_are_not_guessed(self):
        from chatbot.official_reports import report_answer
        docs=[self.report('2025년 — 청구: 1,965\n2025년 — 청구: 2,000')]
        self.assertIsNone(report_answer('정보공개청구 보고서에서 2025년 청구 건수는 몇 건인가요?',docs))
        self.assertIsNone(report_answer('정보공개청구 보고서에서 올해 청구 건수는 몇 건인가요?',docs))

    def test_data_period_is_distinct_from_issued_date(self):
        from chatbot.official_reports import report_answer
        result=report_answer('정보공개청구 보고서는 몇 년 자료를 분석했나요?',[self.report('분석 보고서')])
        self.assertIn('2023-01-01~2025-12-31',result['answer'])
        self.assertIn('작성일: 2026-08-04',result['answer'])
