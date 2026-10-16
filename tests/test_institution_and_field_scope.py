import json
import unittest
from pathlib import Path
from chatbot.query_subject import query_keywords
from chatbot.evidence import is_service_source
from chatbot.structured_answers import structured_brief
from chatbot.concise_answers import course_scope_result

FIXTURES = Path(__file__).parent / 'fixtures'


def fixture(file, key=None):
    d=json.loads((FIXTURES/file).read_text(encoding='utf8'))
    return d[key] if key else d


class InstitutionAndFieldScopeTests(unittest.TestCase):
    def test_office_address_and_phone_are_one_institution_topic(self):
        q='사하구청 주소와 대표전화 번호가 궁금해요.'
        kw=query_keywords(q,['구청','대표','전화번호'])
        self.assertEqual(kw,{'구청'})
        d=fixture('accuracy_p_sources_20261016.json','office')
        self.assertTrue(is_service_source(q,d,kw))
        r=structured_brief(q,d,d['content'],kw)
        self.assertIn('낙동대로398번길',r['answer'].replace(' ',''))

    def test_other_facility_address_cannot_locate_office(self):
        q='사하구청 주소와 대표전화 번호가 궁금해요.'
        d=fixture('accuracy_p_sources_20261016.json','unrelated')
        self.assertFalse(is_service_source(q,d,{'구청'}))

    def test_fabricated_congratulatory_grant_cannot_borrow_birth_policy(self):
        d=fixture('accuracy_p_sources_20261016.json','birth')
        self.assertFalse(is_service_source('사하구 새가족우주축하금 99만원 신청 방법 알려줘.',d,{'출산축하'}))
        self.assertTrue(is_service_source('출산지원금 신청 방법 알려줘.',d,query_keywords('출산지원금 신청 방법 알려줘.',['출산지원금','신청','방법'])))

    def test_income_percentage_keeps_all_eligibility_requirements(self):
        d=fixture('accuracy_m_sources_U018.json')
        q='임신부 영양플러스 신청 소득 기준이 몇 퍼센트인지 알려줘.'
        r=structured_brief(q,d,d['content'],{'영양플러스'})
        for word in ('80%','사하구민','6개월','영양위험'):
            self.assertIn(word,r['answer'])
        self.assertNotIn('가구원 수로 산정함',r['answer'])

    def test_meaning_word_is_a_requested_field_not_an_unknown_entity(self):
        d=fixture('accuracy_o_sources_20261016.json','charter')
        q='행정서비스헌장의 의미가 뭔지 알고 싶어요.'
        r=structured_brief(q,d,d['content'],{'행정서비스헌장'})
        self.assertIsNotNone(r)
        self.assertIn('약속하는 제도',r['answer'])

    def test_explicit_youth_visit_reservation_matches_its_program(self):
        d=fixture('accuracy_n_sources_20261016.json','smoking')
        q='금연클리닉 청소년 방문 예약은 꼭 필요해요?'
        r=structured_brief(q,d,d['content'],{'금연','클리닉'})
        self.assertIsNotNone(r)
        self.assertIn('청소년은 예약 필수',r['answer'])
        self.assertNotIn('1544',r['answer'])

    def test_general_public_education_does_not_need_audience_confirmation(self):
        q='정보화교육이 무료 교육인지 궁금해요.'
        self.assertIsNone(course_scope_result(q,'교육대상: 구민 누구나 가능'))
        d=fixture('accuracy_o_sources_20261016.json','digital')
        r=structured_brief(q,d,d['content'],{'정보화교육'})
        self.assertIn('무료',r['answer'])
        self.assertFalse(r.get('is_clarification'))

    def test_eligibility_keeps_same_program_financial_restriction(self):
        d=fixture('accuracy_n_sources_20261016.json','tax')
        r=structured_brief('마을세무사 이용 대상이 누구인가요?',d,d['content'],{'마을세무사'})
        self.assertIn('이용이 어려운 구민',r['answer'])
        self.assertIn('재산보유자',r['answer'])
        self.assertIn('제한',r['answer'])


if __name__=='__main__':
    unittest.main()
