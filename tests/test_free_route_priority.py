import unittest
from unittest.mock import Mock

from chatbot.structured_answers import structured_brief
from chatbot.grounded_planner import answer_with_grounded_model


RULE=('처리방법 처리업체에 직접 전화(☎ 266-1170~1) 또는 문자 접수(051-266-1170~1) '
 '카카오톡 플러스친구(맑은사하환경) 1:1톡 접수 아래 물품중 냉장고, 텔레비젼, 세탁기, '
 '에어컨 및 1m이상 가스오븐렌지, 공기청정기, 복사기, 런닝머신은 무상수거 '
 '(콜센터 1599-0903) 단, 원형훼손제품은 제외 (유상 처리)')
BODY='## 폐기물\n#### 대형 폐기물 배출 · 처리안내\n'+RULE+'\n'+(
 '가전제품 / 냉장고 / 500ℓ이상 — 품 명: 냉장고\n'
 '가전제품 / 냉장고 / 500ℓ이상 — 규 격: 500ℓ이상\n'
 '가전제품 / 냉장고 / 500ℓ이상 — 수 수 료 / 조 정 후 / 계: 20,000\n'
 '가전제품 / 냉장고 / 300ℓ이상 — 품 명: 냉장고\n'
 '가전제품 / 냉장고 / 300ℓ이상 — 수 수 료 / 조 정 후 / 계: 15,000')


class FreeRoutePriorityTests(unittest.TestCase):
    def test_request_noun_survives_different_morphological_segmentation(self):
        from chatbot.query_subject import query_keywords
        complete=query_keywords('냉장고 무료 방문수거 신청은 어디로 해요?',
                               ['냉장고','무상','방문','수거','신청'])
        split=query_keywords('냉장고 무상 방문수거는 어디로 신청해요?',
                            ['냉장고','무상','방문','수','거','신청'])
        self.assertEqual(complete,split)
        self.assertIn('수거',split)

    def test_unrelated_character_fragment_is_not_a_collection_request(self):
        from chatbot.query_subject import query_keywords
        self.assertNotIn('수거',query_keywords('소수거주민 지원이 있나요?',['소수거주민','지원']))

    def test_without_reservation_is_a_condition_not_a_cost_question(self):
        from chatbot.answer_goal import answer_goal, requested_goals
        q='무료 법률상담은 예약 없이 아무 때나 찾아가면 되나요?'
        self.assertEqual(answer_goal(q),'conditions')
        self.assertEqual(requested_goals(q),('conditions',))
        body='## 무료법률상담안내\n방법 : 전화예약 후 방문상담. 사전 전화예약 필수. 상담일정 : 매월 2, 4주 수요일 오후2시~5시'
        result=structured_brief(q,{'content':body,'metadata':{'title':'무료법률상담안내'}},body,{'법률상담'})
        self.assertIsNotNone(result)
        self.assertIn('예약 필수',result['answer'])
        self.assertIn('수요일',result['answer'])

    def doc(self,body=BODY):
        return {'content':body,'metadata':{'title':'폐기물',
         'url':'https://www.saha.go.kr/portal/contents.do?mId=0405050103',
         'source_type':'crawled_page',
         'last_checked_at':'2026-10-16'}}

    def test_explicit_free_route_keeps_exclusion_before_paid_size_fees(self):
        q='냉장고 무료 방문수거 신청은 어디로 해요?'
        result=structured_brief(q,self.doc(),BODY,{'냉장고','무상','방문','수거'})
        self.assertIsNotNone(result)
        self.assertIn('1599-0903',result['answer'])
        self.assertIn('원형훼손제품은 제외 (유상 처리)',result['answer'])
        self.assertNotIn('20,000',result['answer'])
        self.assertFalse(result.get('degraded',False))

    def test_complete_source_route_does_not_need_model_selection(self):
        q='냉장고 무료 방문수거 신청은 어디로 해요?'
        llm=Mock()
        result=answer_with_grounded_model(q,[self.doc()],None,{'냉장고','무상','방문','수거'},llm)
        self.assertIsNotNone(result)
        llm.model_copy.assert_not_called()

    def test_other_named_product_cannot_inherit_free_route(self):
        body=BODY.replace('아래 물품중 냉장고,','아래 물품중')
        result=structured_brief('냉장고 무료 방문수거 신청은 어디로 해요?',self.doc(body),body,{'냉장고','무상','방문','수거'})
        self.assertIsNone(result)

    def test_paid_fee_question_is_not_silently_changed_to_free_route(self):
        result=structured_brief('냉장고 500ℓ이상 처리 수수료는 얼마인가요?',self.doc(),BODY,{'냉장고'})
        self.assertIsNotNone(result)
        self.assertIn('20,000',result['answer'])
        self.assertNotIn('1599-0903',result['answer'])


if __name__=='__main__':unittest.main()
