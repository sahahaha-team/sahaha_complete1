import unittest
from chatbot.dialogue_profile import course_audiences, course_audience_conflict, confirmed_audience
from chatbot.response_helpers import build_contextual_search_query, resolve_clarification_reply, build_clarification
from chatbot.evidence import is_service_source
from chatbot.structured_answers import structured_brief

BODY = ('## 소방특화 들락날락\n'
        '▹ 이용대상 : 4세 이상 13세 이하 어린이 ▹ 체험관을 이용하고자 하는 경우 3개월 전 매월 1일 9시부터 예약 신청 가능합니다.\n'
        '### 다른 메뉴\n성인 교육 프로그램 바로가기')
DOC = {'content':BODY, 'metadata':{'title':'소방특화 들락날락', 'source_type':'crawled_page',
       'url':'https://www.saha.go.kr/reserve/contents.do?mId=1207000000'}}

class CourseParticipantTests(unittest.TestCase):
    def test_adult_or_out_of_range_age_cannot_borrow_a_child_programme(self):
        for query in ('성인 소방 체험 신청 방법','어른 소방 체험 신청 방법','소방 체험 30살 신청 방법',
                      '소방 체험 14살 신청 방법','소방 체험 신청 방법 (확인대상: 성인)'):
            with self.subTest(query=query):
                self.assertFalse(is_service_source(query,DOC,{'소방'}))
                result=structured_brief(query,DOC,BODY,{'소방'})
                self.assertIsNotNone(result)
                self.assertIn('확인되지',result['answer'])
                self.assertNotIn('9시부터',result['answer'])
    def test_in_range_child_still_uses_the_real_child_programme(self):
        for query in ('소방 체험 아이는 8살 신청 방법','아이는8살이고 성인 보호자가 동반하는 소방 체험 신청'):
            self.assertTrue(is_service_source(query,DOC,{'소방'}))
            self.assertFalse(course_audience_conflict(query, course_audiences(BODY.splitlines())))
    def test_audience_only_reply_without_pending_question_keeps_the_course(self):
        previous='소방특화 들락날락 체험 신청방법 8살'
        query=build_contextual_search_query('아니 성인이에요',[{'role':'user','content':previous}])
        self.assertIn('소방특화',query)
        self.assertEqual(confirmed_audience(query),'성인')
        self.assertNotIn('8살',query)
        updated=build_contextual_search_query('아니 아이가 8살',[{'role':'user','search_query':query,'content':'성인'}])
        self.assertIn('소방특화',updated)
        self.assertIn('8살',updated)
        self.assertNotIn('성인',updated)
    def test_pending_participant_replaces_older_demographic_only(self):
        query='소방 체험 신청 방법 어린이 8살'
        pending={**build_clarification('소방 체험 어떻게 신청해'),'query':query}
        result=resolve_clarification_reply('성인',pending)
        self.assertEqual(confirmed_audience(result),'성인')
        self.assertNotIn('8살',result)
        self.assertNotIn('어린이',result)
    def test_adult_source_and_unrestricted_resident_source_remain_available(self):
        for body in ('## 소방 교육\n이용대상: 18세 이상 성인\n신청방법: 공식 홈페이지 신청',
                     '## 소방 교육\n이용대상: 주민 누구나\n신청방법: 공식 홈페이지 신청'):
            self.assertTrue(is_service_source('소방 교육 신청 방법 (확인대상: 성인)',{**DOC,'content':body},{'소방'}))

    def test_facility_phone_shortcut_does_not_ignore_an_explicit_participant(self):
        from unittest.mock import patch
        from datetime import datetime,timezone
        from chatbot.facility_contact import facility_contact
        row={'content':BODY+'\n전화번호: 051-271-6835','raw_html':'','last_checked_at':datetime.now(timezone.utc).isoformat()}
        with patch('database_db.raw_pages.read_raw_pages',return_value=[row]):
            result=facility_contact('성인 소방특화 들락날락 체험 문의 전화번호',object())
            self.assertTrue(result['degraded'])
            self.assertEqual(result['evidence']['status'],'insufficient')
            self.assertNotIn('051-271-6835',result['answer'])

    def test_verified_facility_url_can_resolve_an_elided_phone_but_not_an_older_source(self):
        history=[{'role':'user','content':'소방 체험 8살 신청 방법'},
                 {'role':'assistant','content':'대상 안내','sources':[{'url':DOC['metadata']['url']}]}]
        query=build_contextual_search_query('그럼 전화번호는?',history)
        self.assertIn('소방특화',query)
        self.assertIn('8살',query)
        history[-1]['sources'] = '["'+DOC['metadata']['url']+'"]'
        self.assertIn('소방특화',build_contextual_search_query('그럼 전화번호는?',history))
        history += [{'role':'user','content':'성인','search_query':'소방 체험 신청 (확인대상: 성인)'},
                    {'role':'assistant','content':'근거 부족','sources':[]}]
        query=build_contextual_search_query('그럼 장소는?',history)
        self.assertNotIn('소방특화',query)
        self.assertEqual(confirmed_audience(query),'성인')

if __name__=='__main__': unittest.main()
