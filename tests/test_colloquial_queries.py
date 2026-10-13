import unittest
from unittest.mock import Mock
from bs4 import BeautifulSoup

from chatbot.answer_goal import answer_goal, requested_goals
from chatbot.query_subject import normalize_query, subject_query, query_keywords, fallback_keywords
from chatbot.response_helpers import build_clarification, resolve_clarification_reply, build_contextual_search_query
from chatbot.evidence_decision import document_decision
from chatbot.semantic_ranker import eligible_candidates, text_hash, source_hash
from config import RAG_RERANK_MODEL
from chatbot.official_content import official_html_text
from chatbot.structured_answers import structured_brief
from chatbot.grounded_planner import answer_with_grounded_model
from crawler.saha_crawler import SahaCrawler


def source(title, body, url='https://www.saha.go.kr/portal/contents.do?mId=test'):
    return {'content':body,'metadata':{'title':title,'url':url,'source_type':'crawled_page'}}


class ColloquialQueryTests(unittest.TestCase):
    def test_state_tail_preserves_bare_question_intent(self):
        for subject in ('자전거 전용 도로','공영주차장','소방교육'):
            for suffix in (' 어떻게 돼?',' 어떻게 되나요?',' 어떻게돼요?',' 어떻게 됩니까?'):
                self.assertEqual(requested_goals(subject+suffix), requested_goals(subject))
                self.assertEqual(subject_query(subject+suffix),subject_query(subject))
                self.assertEqual(normalize_query(subject+suffix),normalize_query(subject))

    def test_state_tail_keeps_explicit_action_and_compound_fields(self):
        self.assertEqual(requested_goals('주민등록증 발급 절차는 어떻게 돼?'),('method',))
        self.assertEqual(requested_goals('보건소 진료시간과 위치는 어떻게 되나요?'),('hours','location'))
        self.assertEqual(answer_goal('소방교육 어떻게 받아?'),'method')
        self.assertEqual(answer_goal('화재 어떻게 신고해?'),'method')
        self.assertEqual(answer_goal('자전거도로 이용비용은 어떻게 돼?'),'cost')

    def test_abbreviation_keeps_issuance_subject_after_morphology(self):
        for query in ('민증 발급 절차 알려줘','민증발급 절차 알려줘','주민등록증 발급 절차 알려줘'):
            self.assertEqual(query_keywords(query,['주민','등록증','발급','절차']),{'주민등록증'})
            self.assertIn('주민등록증',normalize_query(query))
        self.assertEqual(normalize_query('시민증과 외국인등록증'),'시민증과 외국인등록증')

    def test_identity_lifecycle_one_question_and_short_followup(self):
        q='민증 발급 절차 알려줘';pending=build_clarification(q)
        self.assertIn('재발급',pending['answer'])
        pending['query']=q
        for reply in ('처음 발급이야','재발급이야'):
            resolved=resolve_clarification_reply(reply,pending)
            self.assertIn(q,resolved)
            self.assertIsNone(build_clarification(resolved))
        self.assertEqual(resolve_clarification_reply('여권 준비물 알려줘',pending),'여권 준비물 알려줘')

    def test_elided_map_followup_keeps_topic_without_changing_a_new_topic(self):
        history=[{'role':'user','content':'자전거 전용 도로 어떻게 돼?', 'search_query':'자전거 전용 도로'},
                 {'role':'assistant','content':'공식 자전거 도로 현황도에서 확인하세요.'}]
        q=build_contextual_search_query('현황 지도 보고 싶어',history)
        self.assertIn('자전거',q)
        self.assertEqual(answer_goal(q),'reference')
        self.assertIsNone(build_clarification(q))
        self.assertIsNotNone(build_clarification('현황 지도 보고 싶어'))
        for new in ('민방위 비상시설 지도 보여줘','비상급수시설 현황 지도 보고 싶어','주차장 지도 보고 싶어','소방교육 신청 방법 알려줘'):
            self.assertEqual(build_contextual_search_query(new,history),new)

    def test_health_certificate_method_does_not_assume_existing_test(self):
        pending=build_clarification('보건증 어떻게 받아?')
        self.assertIn('처음 검사',pending['answer'])
        self.assertIn('검사 후',pending['answer'])
        pending['query']='보건증 어떻게 받아?'
        for reply in ('처음이야','검사는 했어'):
            resolved=resolve_clarification_reply(reply,pending)
            self.assertIn('보건증',resolved)
            self.assertIsNone(build_clarification(resolved))
        for q in ('보건증 검사 후 온라인 발급 방법','보건증 수수료 알려줘','보건증 검사 준비물'):
            self.assertIsNone(build_clarification(q))

    def test_fire_subject_cannot_be_replaced_even_with_high_semantic_score(self):
        q='소방교육 어떻게 받아?';keys=query_keywords(q,['소방','교육'])
        self.assertEqual(keys,{'소방'})
        for title in ('정신건강 관리','영유아 건강검진'):
            doc=source(title,'## '+title+'\n이용방법: 보건소 방문 신청')
            doc['_semantic_support']={'model':RAG_RERANK_MODEL,'query_hash':text_hash(q),
                'source_hash':source_hash(doc),'logit':5,'margin':4,'terms':[title]}
            self.assertEqual(eligible_candidates(q,[doc],keys),[])
            self.assertFalse(document_decision(q,doc,keys)['relevant'])

    def test_identity_source_is_not_passport_or_other_lifecycle(self):
        body='## 여권발급\n신분증: 주민등록증\n신청방법: 방문 신청'
        self.assertFalse(document_decision('민증 발급 방법',source('여권발급안내',body),{'주민등록증'})['relevant'])
        new=source('주민등록증 발급신청','## 주민등록증 발급신청\n제출처: 동 행정복지센터')
        old=source('주민등록증 재발급신청','## 주민등록증 재발급신청\n제출처: 동 행정복지센터')
        self.assertFalse(document_decision('주민등록증 재발급 절차',new,{'주민등록증'})['relevant'])
        self.assertFalse(document_decision('주민등록증 처음 발급 절차',old,{'주민등록증'})['relevant'])

    def test_additional_pages_are_refresh_targets_without_answer_text(self):
        from scripts.ingest_official_materials import official_page_targets
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            urls={url for _,url in official_page_targets(Path(tmp))}
        self.assertIn('https://www.saha.go.kr/portal/civil/view.do?civilId=1626&mId=0103080100',urls)
        self.assertIn('https://www.saha.go.kr/portal/civil/view.do?civilId=1625&mId=0103080100',urls)
        self.assertIn('https://www.saha.go.kr/portal/civil/view.do?civilId=1785&mId=0103080100',urls)

    def test_submission_procedure_keeps_documents_deadline_and_exception(self):
        body=('## 전입신고\n제출처: 신 거주지 동 행정복지센터\n'
              '신청서 및 구비서류: 전입신고서 1부\n신청서 및 구비서류: 신분증 등\n'
              '신청서 및 구비서류: ※ 구분에 따라 추가 지참서류 확인 필요\n'
              '유의사항: 전입한 날부터 14일 이내에 전입신고를 하여야 합니다.')
        result=structured_brief('전입신고 절차 어떻게 돼?',source('전입신고',body),body,{'전입신고'})
        for term in ('신 거주지','전입신고서','신분증','추가 지참서류','14일 이내'):
            self.assertIn(term,result['answer'])
        self.assertLessEqual(len(result['answer']),480)

    def test_actual_map_rule_is_left_for_factual_source_reader(self):
        from chatbot.reference_answers import reference_answer
        body='## 자전거 도로 현황도\n통행 규칙: 자동차는 통행을 금지합니다.'
        self.assertIsNone(reference_answer('자전거도로 통행 규칙 알려줘',source('자전거 도로 현황도',body),body,{'자전거'}))

    def test_dedicated_safety_facility_does_not_become_other_services(self):
        from chatbot.evidence import is_service_source
        body=('## 이용안내\n### 이용정보\n주소: 사하구 장평로\n이용대상: 4세 이상 13세 이하 어린이\n'
              '예약방법: 매월 1일부터 예약 신청 가능합니다.\n#### 공간안내\n2F 소방안전교육센터(심폐소생술 체험관)')
        doc=source('이용안내',body,'https://www.saha.go.kr/reserve/contents.do?mId=1207000000')
        self.assertTrue(is_service_source('어린이 소방체험 예약 방법',doc,{'소방'}))
        self.assertFalse(is_service_source('소방교육 어떻게 받아?',source('정신건강 관리',body),{'소방'}))
        self.assertFalse(is_service_source('소방교육 어떻게 받아?',source('이용안내',body+'\n### 정신건강\n이용방법: 전화 예약'),{'소방'}))

    def test_bicycle_map_same_navigation_without_fabricated_designation(self):
        doc=source('자전거 도로 현황도','## 자전거 도로 현황도\n사하구 자전거 도로 현황도')
        answers=[]
        for q in ('자전거 전용 도로','자전거 전용 도로 어떻게 돼?','자전거도로 어떻게 되나요?'):
            result=answer_with_grounded_model(q,[doc],None,{'자전거'},Mock())
            self.assertEqual(result['answer_method'],'official_reference')
            answers.append(result['answer'])
        self.assertEqual(len(set(answers)),1)
        from chatbot.reference_answers import reference_answer
        for q in ('자전거 전용도로 통행 규칙 알려줘','자전거만 통행 가능해?','총 길이 몇 km야?'):
            result=reference_answer(q,doc,doc['content'],{'자전거'})
            self.assertTrue(result['degraded'])
            self.assertIn('근거가 부족',result['answer'])
            self.assertFalse(result['is_clarification'])

    def test_road_topic_is_not_replaced_by_bicycle_accident_insurance(self):
        q='자전거 전용도로 통행 규칙 알려줘'
        keys=query_keywords(q,['자전거','전용','도로','통행','규칙'])
        self.assertEqual(keys,{'자전거도로'})
        insurance=source('구민안전보험','## 구민안전보험\n자전거 사고 — 보장내용: 자전거 사고 보상')
        self.assertFalse(document_decision(q,insurance,keys)['relevant'])
        self.assertEqual(eligible_candidates(q,[insurance],keys),[])
        pending=[{'role':'user','content':'자전거 전용도로 어떻게 돼?', 'search_query':'자전거 전용도로'}]
        self.assertIn('자전거도로',build_contextual_search_query('현황 지도 보고 싶어',pending))

    def test_course_scope_cannot_be_assumed_from_an_application_question(self):
        body='## 공동주택 관리 안내\n### 어린이 놀이시설 안전관리\n신청방법: 각 기관사이트의 신청서 이용\n### 관리주체 소방 및 방범교육\n대 상 : 의무관리대상 공동주택 경비책임자\n장 소 : 사하구청(예정)\n일 시 : 상반기 중 예정'
        doc=source('공동주택 관리 안내',body)
        result=structured_brief('소방교육 어떻게 받아?',doc,body,{'소방'})
        self.assertTrue(result['is_clarification'])
        self.assertIn('경비책임자',result['answer'])
        self.assertNotIn('사하구청(예정)',result['answer'])
        for q in ('소방 안전교육 신청 방법 알려줘','소방교육 받고 싶어요','화재 예방 교육 신청하려면?'):
            q=normalize_query(q)
            result=structured_brief(q,doc,body,{'소방'})
            self.assertTrue(result['is_clarification'])
            self.assertIn('경비책임자',result['answer'])
            self.assertNotIn('기관사이트',result['answer'])
        result=structured_brief('일반 주민 소방교육 어떻게 받아?',doc,body,{'소방'})
        self.assertTrue(result['degraded'])
        self.assertIn('확인되지',result['answer'])

    def test_detail_form_retains_field_pairs_and_discards_misleading_caption(self):
        html='''<div id="contents"><h2>민원편람/서식안내</h2><div id="conts">
        <form id="detailForm"><table class="tableSt_view">
        <caption>인감증명발급신청</caption><tr><th class="title" colspan="4">주민등록증 발급신청</th></tr>
        <tr><th>제출처</th><td>동 행정복지센터</td><th>처리기간</th><td>즉시</td></tr>
        <tr><th>신청서 및 구비서류</th><td colspan="3">신청서 1부<br>사진 1매<br>학생증 또는 본인확인 증명서</td></tr>
        <tr><th>업무처리 흐름도</th><td colspan="3">신청 - 접수 - 제작(2주 정도 소요) - 교부</td></tr>
        </table></form><form>주민등록증을 즉시 수령</form></div></div>'''
        body=official_html_text(html)
        self.assertIn('제출처: 동 행정복지센터',body)
        self.assertIn('처리기간: 즉시',body)
        self.assertNotIn('인감증명',body)
        self.assertNotIn('즉시 수령',body)
        self.assertEqual(body.count('신청서 및 구비서류:'),3)
        self.assertEqual(object.__new__(SahaCrawler)._extract_title(BeautifulSoup(html,'lxml')),'주민등록증 발급신청')
        q='주민등록증 처음 발급 절차 알려줘'
        result=structured_brief(q,source('주민등록증 발급신청',body),body,{'주민등록증'})
        self.assertIn('제작(2주 정도 소요)',result['answer'])
        self.assertNotIn('즉시',result['answer'])


if __name__ == '__main__':
    unittest.main()
