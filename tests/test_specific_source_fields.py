import json
import unittest
from pathlib import Path
from chatbot.query_subject import query_keywords
from chatbot.evidence import is_service_source, topic_support
from chatbot.structured_answers import structured_brief, field_matches, explicit_table_answer
from chatbot.concise_answers import _source_units

FIXTURE = Path(__file__).parent / 'fixtures' / 'accuracy_o_sources_20261016.json'


def doc(key):
    return json.loads(FIXTURE.read_text(encoding='utf8'))[key]


class SpecificSourceFieldsTests(unittest.TestCase):
    def test_first_issue_marker_is_lifecycle_not_required_literal_in_original(self):
        q = '주민등록증 신규 발급이 처음인데 신청부터 받기까지 어떻게 진행돼요?'
        kw = query_keywords(q, ['주민등록증', '신규', '발급', '신청', '진행'])
        self.assertEqual(kw, {'주민등록증'})
        self.assertTrue(topic_support(doc('id'), kw)[0])
        wrong = {'content':'신분증을 지참하세요.', 'metadata':{'title':'주민등록증 재발급신청'}}
        self.assertFalse(is_service_source(q, wrong, kw))

    def test_damaged_item_cannot_use_general_free_membership_table(self):
        q = '원형이 훼손된 에어컨도 폐가전 무료수거 대상에 들어가나요?'
        d = doc('free')
        self.assertIsNone(explicit_table_answer(q, _source_units(d['content'].splitlines()), d['metadata']['title']))
        self.assertFalse(field_matches('cost', '에어컨은 무상수거 가능', q))
        self.assertTrue(field_matches('eligibility', '제외대상: 원형훼손제품', q))
        r = structured_brief(q, d, d['content'], {'에어컨','폐가전','무상'})
        self.assertTrue(r is None or r.get('degraded') or '훼손' in r['answer'])

    def test_embedded_applicant_age_in_complete_cell(self):
        d = doc('travel')
        q = '해외여행클리닉 말라리아 처방전은 만 몇 세부터 받을 수 있나요?'
        r = structured_brief(q, d, d['content'], {'말라리아','해외여행클리닉'})
        self.assertIsNotNone(r)
        self.assertIn('만 15세', r['answer'])
        self.assertNotIn('장티푸스', r['answer'])

    def test_phone_inside_land_notice_is_not_calendar_month(self):
        q = '개별공시지가 이의신청은 몇 월에 해요?'
        self.assertFalse(field_matches('schedule', '신청방법: 개별공시지가 담당(051-220-4755)으로 연락', q))
        d = doc('land')
        r = structured_brief(q, d, d['content'], {'공시지가'})
        self.assertIn('6월', r['answer'])
        self.assertIn('11월', r['answer'])
        self.assertNotIn('의견서', r['answer'])

    def test_definition_has_meaning_not_only_operating_history(self):
        d = doc('charter')
        r = structured_brief('행정서비스헌장이 어떤 제도인지 설명해 주세요.', d, d['content'], {'행정서비스헌장'})
        self.assertIn('약속하는 제도', r['answer'])

    def test_information_education_does_not_borrow_lifelong_program_fee(self):
        q = '사하구 정보화교육은 수강료가 얼마인가요?'
        kw = query_keywords(q, ['정보화교육','수강료'])
        self.assertEqual(kw, {'정보화교육'})
        self.assertTrue(topic_support(doc('digital'), kw)[0])
        self.assertFalse(topic_support(doc('lifelong'), kw)[0])
        d = doc('digital')
        r = structured_brief(q, d, d['content'], kw)
        self.assertIn('무료', r['answer'])
        self.assertFalse(r.get('degraded'))

    def test_conflicting_clinic_floor_is_quarantined_until_source_changes(self):
        from chatbot.source_warnings import reviewed_source
        d = json.loads((FIXTURE.parent / 'accuracy_n_sources_20261016.json').read_text(encoding='utf8'))['health']
        d['metadata']['url'] = 'https://www.saha.go.kr/health/contents.do?mId=0201020000'
        body = '## 물리치료실\nStep 4. 치료 1층 물리치료실\n진료장소 : 3층 물리치료실'
        safe, meta = reviewed_source(body, d['metadata'])
        self.assertIn('location', meta['unverified_fields'])
        self.assertNotIn('1층', safe)
        self.assertNotIn('3층', safe)
        safe, meta = reviewed_source('## 물리치료실\n진료장소 : 3층 물리치료실', d['metadata'])
        self.assertNotIn('unverified_fields', meta)


if __name__ == '__main__':
    unittest.main()
