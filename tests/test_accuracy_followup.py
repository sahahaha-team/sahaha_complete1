"""Additional real-HTTP failures: request fields, roles and conditions."""
import unittest
from chatbot.answer_goal import answer_goal, requested_goals
from chatbot.structured_answers import field_matches, structured_brief
from chatbot.concise_answers import concise_source_answer
from chatbot.grounded_planner import render_plan
from chatbot.source_answers import focused_section
from chatbot.source_scope import focus_terms
from chatbot.evidence import is_time_compatible
from chatbot.emergency_guidance import answer_emergency_question
from chatbot.response_helpers import build_clarification
import tests.test_contact_directory as contact_fixtures


def doc(body, title='여권발급안내', mid='0104020000'):
    return {'content':body,'metadata':{'title':title,'url':'https://www.saha.go.kr/portal/contents.do?mId='+mid,
                                     'source_type':'crawled_page'}}


class FollowupFieldTests(unittest.TestCase):
    def test_explicit_fields_win_over_incidental_application_actions(self):
        cases={
            '만 18세 대학생 여권을 부모님이 대신 신청해도 돼요?':'conditions',
            '여권 신분증은 원본 대신 휴대폰 사진이면 되나요?':'conditions',
            '주민등록증은 만 17세부터 맞나요?':'eligibility',
            '인감증명서 대리로 떼려면 뭐가 필요해요?':'documents',
            '소파 버리는 수수료 얼마예요?':'cost',
            '첫만남이용권은 현금으로 계좌에 들어와요?':'conditions',
            '자동차세 연납 신청은 어느 달에 가능한가요?':'schedule',
            '금연클리닉에서 보조제도 지원해 주나요?':'services',
            '외국인도 희망도서를 신청할 수 있나요?':'conditions',
        }
        for q,wanted in cases.items():
            with self.subTest(q=q): self.assertEqual(answer_goal(q),wanted)
        self.assertEqual(requested_goals('냉장고 무료 방문수거 신청은 어디로 해요?'),('method','cost'))
        self.assertEqual(requested_goals('소파 버리는 수수료 얼마예요?'),('cost',))

    def test_country_particle_is_not_photo_width(self):
        u='단수여권(PP) : 1년의 유효 기간이 부여되지만 1회에 한하여 여행할 수 있고 여행 출발지 국가로의 재입국 시 효력 상실'
        self.assertFalse(field_matches('specifications',u,'여권 사진 규격'))
        self.assertTrue(field_matches('specifications','여권 사진 가로3.5cm 세로4.5cm','여권 사진 규격'))
        self.assertIsNone(structured_brief('여권 사진 규격',doc('## 여권의 종류\n'+u), '## 여권의 종류\n'+u,{'여권'}))

    def test_proxy_permission_is_not_online_application_method(self):
        q='만18세 여권은 부모님이 대신 신청해도 돼요?'
        self.assertFalse(field_matches('conditions','온라인 여권 민원 서비스(정부24) 대상민원 : 여권 재발급',q))
        self.assertFalse(field_matches('conditions','만18세 미만 미성년자 친권자가 신청',q))
        self.assertTrue(field_matches('conditions','본인이 직접 방문신청(미성년자 제외)',q))
        body='## 여권발급안내\n### 여권발급 주요 내용\n본인이 직접 방문신청(미성년자 제외)\n### 신규발급\n친권자 신분증\n### 여권발급 기록 증명서\n대리인 신청 시 신분증 사본 가능'
        focused=focused_section(q,'https://www.saha.go.kr/portal/contents.do?mId=0104020000',body)
        self.assertIn('본인이 직접',focused)
        self.assertNotIn('사본 가능',focused)
        q='만 18세가 된 대학생 여권은 부모님이 대신 신청해도 돼요?'
        result=structured_brief(q,doc(body),'## 여권발급안내\n'+focused,{'여권'})
        self.assertIsNotNone(result)
        self.assertIn('본인이 직접',result['answer'])

    def test_residency_prerequisite_stays_with_supplement_schedule(self):
        body='## 임산부건강관리\n### 엽산제, 철분제 지원\n대상 : 주민등록상 부산 사하구에 거주하는 임산부\n내용 엽산제 : 임신 12주까지 (1인 최대 2개월분) 철분제 : 임신 16주부터 (1인 최대 5개월분)'
        q='임산부 엽산제는 임신 몇 주까지 지원해요?'
        result=structured_brief(q,doc(body,'임산부건강관리'),body,{'임산부'})
        self.assertIn('사하구에 거주',result['answer'])
        self.assertIn('12주',result['answer'])

    def test_specific_unseen_food_cannot_be_answered_with_other_exclusions(self):
        q='라면 국물은 음식물쓰레기에 버려도 돼요?'
        body='## 음식물쓰레기\n### 배출요령\n음식물쓰레기 — 넣어서는 안되는 물질: 동물의 뼈, 조개류의 껍질'
        document=doc(body,'폐기물','0405050102')
        self.assertIsNone(structured_brief(q,document,body,{'음식물쓰레기'}))
        original='\n'.join('> '+u for u in body.splitlines())
        r=concise_source_answer(q,original,[document],{'음식물쓰레기'})
        self.assertTrue(r.get('degraded') or r.get('is_clarification'))
        p={'units':body.splitlines(),'body':body,'document':document}
        self.assertIsNone(render_plan(q,{'mode':'answer','source':0,'units':[2]},[p],{'음식물쓰레기'}))

    def test_old_rule_mentioned_to_ask_about_now_is_not_a_historical_request(self):
        d=doc('개인별 연간 최대 500만원(2025년부터 2천만원까지 가능)','고향사랑기부')
        self.assertTrue(is_time_compatible('2024년에 500만원이라던데 지금도 그대로예요?',d))
        self.assertFalse(is_time_compatible('2024년 고향사랑기부 실적 통계를 알려줘',d))
        q='2024년에 고향사랑기부 상한이 500만원이라던데 지금도 그대로예요?'
        body='## 사하 고향사랑기부제\n### 누가 기부할 수 있나요?\n개인별 연간 최대 500만원(지자체 합산) 기부 가능(2025년부터 2천만원까지 가능)\n### 기부자 혜택\n세액공제 : 10만원 이하 100%'
        result=structured_brief(q,doc(body,'사하 고향사랑기부제'),body,{'고향사랑기부'})
        self.assertIn('2천만원',result['answer'])
        self.assertNotIn('세액공제',result['answer'])

    def test_certificate_name_and_proxy_papers_match_their_own_heading(self):
        from chatbot.query_subject import fallback_keywords
        q='동 주민센터에서 인감증명서를 대리로 떼려면 뭐가 필요해요?'
        self.assertIn('인감증명',fallback_keywords(q))
        body='## 민원실 이용안내\n### 증명민원 통합발급\n#### 인감증명발급\n구비서류 본 인 : 신분증 위임을 받은 자 : 신분증, 위임장, 위임자 신분증\n#### 가족관계증명서 발급\n구비서류 : 신청인 신분증'
        r=structured_brief(q,doc(body,'민원실 이용안내','0103010000'),body,{'인감증명'})
        self.assertIsNotNone(r)
        self.assertIn('위임장',r['answer'])
        self.assertNotIn('가족관계증명서',r['answer'])

    def test_polite_request_is_not_an_unknown_service_detail(self):
        self.assertNotIn('부탁',focus_terms('자전거 도로 안내 부탁드립니다'))

    def test_generic_issuing_counter_does_not_hide_certificate_papers(self):
        from chatbot.evidence import is_service_source
        from chatbot.grounded_planner import prepare_evidence
        from chatbot.source_answers import build_source_answer
        body='## 민원실 이용안내\n#### 인감증명발급\n구비서류 : 위임을 받은 자의 신분증, 위임장, 위임자 신분증'
        d=doc(body,'민원실 이용안내','0103010000')
        self.assertTrue(is_service_source('동 주민센터에서 인감증명서 대리 발급 준비물',d,{'인감증명'}))
        self.assertFalse(is_service_source('괴정복지센터 인감증명서 대리 발급 준비물',d,{'인감증명'}))
        self.assertFalse(is_service_source('주민센터 인감증명서 발급 장소',d,{'인감증명'}))
        q='동 주민센터에서 인감증명서를 대리로 떼려면 뭐가 필요해요?'
        self.assertTrue(prepare_evidence(q,[d],None,{'인감증명'}))
        self.assertTrue(build_source_answer([d],None,query=q,topic_keywords={'인감증명'})[0])

    def test_procedure_deadline_keeps_owning_parent_and_extension(self):
        import json
        from pathlib import Path
        f=json.loads((Path(__file__).parent/'fixtures/information_procedure_20261016.json').read_text(encoding='utf8'))
        q='정보공개청구를 내면 공개 여부 결정은 언제 알려주나요?'
        d={'content':f['content'],'metadata':{'title':f['title'],'url':f['url']}}
        r=structured_brief(q,d,f['content'],{'정보공개청구'})
        self.assertIsNotNone(r)
        self.assertIn('청구를 받은 날부터 10일',r['answer'])
        self.assertIn('연장사유',r['answer'])
        body='## 민원실\n### 인감증명발급\n구비서류 : 신분증\n### 가족관계증명서\n수수료 : 1,000원'
        self.assertIsNone(structured_brief('인감증명서 수수료',doc(body,'민원실'),body,{'인감증명'}))

    def test_sofa_fee_requires_missing_size(self):
        self.assertIsNotNone(build_clarification('소파 버리는 수수료 얼마예요?'))
        self.assertIsNone(build_clarification('2인용 소파 수수료 얼마예요?'))

    def test_pregnancy_program_cannot_use_senior_flu_fields(self):
        from chatbot.vaccination import vaccination_section
        url='https://www.saha.go.kr/health/contents.do?mId=0203020000'
        body='인플루엔자 예방접종\n대상 : 65세 이상 어르신\n비용 : 무료\n해외여행자 예방접종'
        self.assertEqual(vaccination_section('임신부 독감 예방접종 무료인가요?',url,body),'')

    def test_gas_incident_is_immediate_but_billing_and_training_are_not(self):
        for q in ['집에서 가스 냄새가 심하게 나는데 민원을 넣으면 되나요?','가스가 새고 있어요 어디 신고해?']:
            r=answer_emergency_question(q)
            self.assertIn('119',r['answer'])
            self.assertIn('조작',r['answer'])
        for q in ['가스요금 지원 부서 알려줘','가스누출 예방교육 신청 방법']:
            self.assertIsNone(answer_emergency_question(q))


class ContactRelationTests(unittest.TestCase):
    def setUp(self):
        fixture=contact_fixtures.ContactDirectoryTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.data,self.ask,self.save=fixture.data,fixture.ask,fixture.save

    def test_ai_and_counselling_in_different_duties_do_not_establish_ai_counselling(self):
        self.data['departments'].append({'name':'일자리정책과','representative_phone':'051-220-4444','contacts':[
            {'title':'주무관','phone':'051-220-4486','duties':'○찾아가는 일자리상담소 운영\n○취업교육 운영(AI스마트폰 취업준비반)', 'keywords':['ai','상담','취업교육']}]})
        self.save()
        result=self.ask('AI 상담 담당 부서 연락처')
        self.assertTrue(result['is_clarification'])
        self.assertNotIn('4486',result['answer'])

    def test_fax_is_not_replaced_with_a_staff_phone(self):
        r=self.ask('여권 담당자 팩스번호가 전화번호랑 같은가요?')
        self.assertEqual(r['degraded_reason'],'fax_not_verified')
        self.assertIn('팩스번호',r['answer'])
