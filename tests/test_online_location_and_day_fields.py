import json
import unittest
from pathlib import Path
from chatbot.answer_goal import requested_goals, answer_goal
from chatbot.structured_answers import structured_brief
from chatbot.query_subject import fallback_keywords


class OnlineLocationAndDayFieldTests(unittest.TestCase):
    def source(self, name, key=None):
        d=json.loads((Path(__file__).parent/'fixtures'/name).read_text(encoding='utf8'))
        return d[key] if key else d

    def test_online_application_where_is_a_channel_not_a_physical_place(self):
        q='보건증 검사를 받았어요. 인터넷 발급 홈페이지가 어디인가요?'
        self.assertEqual(requested_goals(q),('method',))
        d=self.source('accuracy_t_certificate_20261016.json')
        r=structured_brief(q,d,d['content'],fallback_keywords(q))
        self.assertIsNotNone(r)
        self.assertIn('e-health.go.kr',r['answer'])
        self.assertIn('정상',r['answer'])

    def test_online_word_does_not_erase_explicit_physical_visit_location(self):
        for q in ('인터넷 예약한 보건소의 실제 방문 주소는 어디인가요?', '온라인 신청 후 현장 접수 장소는 어디인가요?'):
            self.assertIn('location',requested_goals(q))

    def test_road_address_is_a_field_not_a_second_unknown_facility(self):
        q='사하구청의 도로명주소와 대표전화가 궁금합니다.'
        d=self.source('accuracy_p_sources_20261016.json','office')
        r=structured_brief(q,d,d['content'],fallback_keywords(q))
        self.assertIsNotNone(r)
        self.assertIn('낙동대로398번길',r['answer'].replace(' ',''))

    def test_spaced_day_question_selects_actual_decision_duration(self):
        d=self.source('accuracy_n_sources_20261016.json','information')
        for phrase in ('몇 일','몇일','며칠'):
            q=f'정보공개청구 공개여부 결정은 {phrase} 이내에 통지하나요?'
            self.assertEqual(answer_goal(q),'schedule')
            r=structured_brief(q,d,d['content'],{'정보공개청구'})
            self.assertIsNotNone(r)
            self.assertIn('10일',r['answer'])
            self.assertIn('문서',r['answer'])

    def test_missing_field_cannot_borrow_from_another_named_program(self):
        d={'content':'## 보건소 안내\n### 금연클리닉\n대상: 금연을 희망하는 지역주민\n### 예방접종\n수수료: 10,000원',
           'metadata':{'title':'보건소 안내','source_type':'crawled_page'}}
        r=structured_brief('금연클리닉 비용이 얼마인가요?',d,d['content'],{'금연','클리닉'})
        self.assertTrue(r is None or '10,000원' not in r['answer'])


if __name__=='__main__':
    unittest.main()
