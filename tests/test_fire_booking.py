import json
from pathlib import Path
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from chatbot.fire_booking import fire_booking, GUIDE, FACILITY
from chatbot.dialogue_profile import course_audiences, course_audience_conflict

DATA=json.loads((Path(__file__).parent/'fixtures/fire_booking_20261026.json').read_text(encoding='utf8'))
ENTRY='''<a onclick="fn_agree_proc()">예약신청</a><script>
function fn_agree_proc(){alert('개인정보의 수집 이용에 동의하지 않을경우 신청이 불가합니다.');
location.href = '/reserve/fireSpec/list.do?mId=1207030000';}</script>'''

class FireBookingTests(unittest.TestCase):
    def answer(self,q,guide=None,parent=None,html=ENTRY,checked=None):
        now=datetime.now(timezone.utc).isoformat()
        rows=[{'url':GUIDE,'content':guide or DATA['guide'],'raw_html':html,'last_checked_at':checked or now},
              {'url':FACILITY,'content':parent or DATA['parent'],'last_checked_at':now}]
        with patch('database_db.raw_pages.read_raw_pages',return_value=rows):return fire_booking(q,object())

    def test_read_authentication_consent_application_and_actual_target(self):
        for q in ('소방 체험 아이는8살 신청 방법','소방특화 들락날락 13살 예약 어떻게 해','소방 교육 아이는8살 신청방법'):
            r=self.answer(q)
            self.assertIsNotNone(r)
            self.assertFalse(r['is_clarification'])
            for t in ('4세 이상 13세 이하','본인인증','개인정보','예약신청','3개월 전','매월 1일 9시','최소 3인'):
                self.assertIn(t,r['answer'])
            self.assertNotIn('잔여',r['answer'])

    def test_unknown_audience_clarifies_adult_and_out_of_range_cannot_book(self):
        self.assertTrue(self.answer('소방특화 들락날락 체험 예약 방법')['is_clarification'])
        for scope in ('성인','30살','3살','14살'):
            r=self.answer('소방특화 들락날락 '+scope+' 체험 신청방법')
            self.assertTrue(r['degraded'])
            self.assertNotIn('예약신청',r['answer'])
        self.assertIsNone(self.answer('소방 교육 성인 신청방법'))

    def test_heading_target_is_owned_without_borrowing_companion_or_other_menu(self):
        values=course_audiences(DATA['guide'].splitlines())
        self.assertEqual(values,['4세 이상 13세 이하 어린이'])
        self.assertTrue(course_audience_conflict('소방 체험 성인 신청방법',values))
        self.assertEqual(course_audiences(['#### 다른 메뉴','성인 프로그램','#### 신청대상 및 인원','▹ 4세 이상 13세 이하 어린이','▹ 개인10명']),values)

    def test_conflicting_target_expired_source_or_missing_controls_cannot_invent_steps(self):
        r=self.answer('소방특화 들락날락 8살 예약방법',parent=DATA['parent'].replace('13세 이하','12세 이하'))
        self.assertTrue(r['degraded'])
        self.assertNotIn('예약신청',r['answer'])
        self.assertIsNone(self.answer('소방특화 들락날락 8살 예약방법',html=''))
        self.assertIsNone(self.answer('소방특화 들락날락 8살 예약방법',checked='2020-01-01T00:00:00Z'))
        self.assertIsNone(self.answer('소방특화 들락날락 8살 예약방법',guide=DATA['guide'].replace('본인인증','인증 정보 없음')))

    def test_field_switches_and_manager_programmes_keep_existing_routes(self):
        for q in ('소방특화 들락날락 전화번호','소방특화 들락날락 8살 장소','소방특화 들락날락 지금 남은 자리',
                  '소방 공동주택 관리자 신청방법','소방특화 들락날락 전화로 신청할 수 있어?'):
            self.assertIsNone(self.answer(q))

    def test_only_registered_pages_of_the_same_facility_bind_an_elided_followup(self):
        from chatbot.response_helpers import build_contextual_search_query
        history=[{'role':'user','content':'아이는8살','search_query':'소방 체험 아이는8살 신청방법'},
                 {'role':'assistant','content':'예약 안내','sources':[{'url':GUIDE},{'url':FACILITY}]}]
        q=build_contextual_search_query('그럼 전화번호는?',history)
        self.assertIn('소방특화',q)
        self.assertIn('8살',q)
        from chatbot.facility_contact import facility_contact
        history += [{'role':'user','content':'그럼 전화번호는?','search_query':q},
                    {'role':'assistant','content':'시설 전화 안내','sources':[{'url':FACILITY}]}]
        location=build_contextual_search_query('장소는?',history)
        row={'url':FACILITY,'content':DATA['parent'],'last_checked_at':datetime.now(timezone.utc).isoformat()}
        with patch('database_db.raw_pages.read_raw_pages',return_value=[row]):
            r=facility_contact(location,object())
        self.assertIn('장평로 270',r['answer'])
        self.assertFalse(r['degraded'])
        history=history[:2]
        history[-1]['sources'].append({'url':'https://www.saha.go.kr/health/contents.do?mId=0103000000'})
        self.assertNotIn('소방특화',build_contextual_search_query('그럼 전화번호는?',history))

if __name__=='__main__':unittest.main()
