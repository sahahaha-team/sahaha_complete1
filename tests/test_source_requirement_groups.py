import copy,json,unittest
from pathlib import Path
from chatbot.evidence import is_service_source
from chatbot.structured_answers import structured_brief
from chatbot.concise_answers import _source_units,condition_indices,concise_source_answer
from chatbot.source_requirements import mandatory_criteria_groups,applicant_qualification_supported
from chatbot.response_helpers import unavailable_capability

FIXTURES=Path(__file__).parent/'fixtures'
def doc(id):return json.loads((FIXTURES/('accuracy_m_sources_'+id+'.json')).read_text(encoding='utf8'))

class RequirementGroupTests(unittest.TestCase):
    def test_named_member_institution_can_find_its_actual_program(self):
        d=doc('U009');q='사하구 작은도서관 희망도서의 월·연 신청가능 권수가 궁금해요.';kw={'작은도서관','희망도서'}
        self.assertTrue(is_service_source(q,d,kw))
        r=structured_brief(q,d,d['content'],kw)
        self.assertIn('월 2권',r['answer']);self.assertIn('15권',r['answer'])

    def test_membership_cannot_establish_another_institution_or_location(self):
        d=doc('U009')
        self.assertFalse(is_service_source('다대도서관 희망도서 신청 한도 알려줘',d,{'희망도서'}))
        self.assertFalse(is_service_source('작은도서관 주소 알려줘',d,{'작은도서관'}))

    def test_sibling_program_membership_cannot_establish_requested_owner(self):
        d=doc('U009');d['content']='## 희망도서\n신청권수: 월 2권\n## 다른 사업\n신청대상: 작은도서관 통합회원'
        self.assertFalse(is_service_source('작은도서관 희망도서 신청권수',d,{'희망도서','작은도서관'}))

    def test_heir_documents_keep_common_id_and_not_proxy_papers(self):
        d=doc('U011');q='조상 땅 찾기 신청 시 상속인이 챙길 구비서류가 궁금해요.'
        r=structured_brief(q,d,d['content'],{'조상땅'})
        self.assertIn('신분증',r['answer']);self.assertIn('제적등본',r['answer'])
        self.assertIn('2008',r['answer']);self.assertNotIn('위임장',r['answer'])

    def test_common_id_closure_is_shared_with_model_and_fallback_readers(self):
        units=_source_units(doc('U011')['content'].splitlines())
        heir=next(i for i,u in enumerate(units) if u.startswith('구비서류: 상속인'))
        selected=[units[i] for i in condition_indices(units,[heir])]
        self.assertTrue(any(u.startswith('신분증') for u in selected))
        self.assertFalse(any('위임장' in u for u in selected))

    def test_all_declared_criteria_are_kept_with_age_income_and_exceptions(self):
        d=doc('U018');q='영양플러스는 영유아도 대상인가요? 소득 기준도 함께 알려주세요.'
        r=structured_brief(q,d,d['content'],{'영양플러스','영유아'})
        for word in ('사하구민','6세 이하','80%','영양위험','6개월','임신부'):
            self.assertIn(word,r['answer'])
        self.assertNotEqual(r['answer'].count('가구원 수로 산정함'),1)

    def test_incomplete_numbered_group_cannot_be_reported_as_all_requirements(self):
        units=['### 신청기준 (아래4가지 조건 모두 만족)','거주기준: 사하구민','소득기준: 중위소득80% 이하']
        self.assertEqual(mandatory_criteria_groups(units),[])

    def test_criteria_group_does_not_invent_unstated_nationality(self):
        d=doc('U018')
        r=structured_brief('외국인 영유아도 영양플러스 신청 대상인가요?',d,d['content'],{'영양플러스','영유아'})
        self.assertIsNone(r)

    def test_fallback_does_not_present_general_criteria_as_nationality_proof(self):
        d=doc('U018');q='외국인 영유아도 영양플러스 신청 대상인가요?'
        original='영양플러스의 공식 안내 원문입니다.\n\n'+'\n'.join('> '+u for u in d['content'].splitlines())
        r=concise_source_answer(q,original,[d],{'영양플러스','영유아','외국인'})
        self.assertTrue(r.get('degraded'));self.assertIn('근거',r['answer'])

    def test_explicit_foreign_applicant_rule_differs_from_household_count(self):
        q='외국인 영유아도 신청 대상인가요?'
        self.assertFalse(applicant_qualification_supported(q,['가구원수: 외국인 배우자도 가구원 수로 산정합니다.']))
        self.assertTrue(applicant_qualification_supported(q,['신청대상: 외국인 영유아 포함.']))

    def test_duties_request_selects_work_not_just_definition(self):
        d=doc('U017');q='부산 사하구 납세자보호관은 어떤 일을 하는지 알려주세요.'
        r=structured_brief(q,d,d['content'],{'납세자보호관'})
        self.assertIsNotNone(r);self.assertIn('고충민원',r['answer']);self.assertIn('기간연장',r['answer'])

    def test_explicit_action_subject_is_not_asked_again(self):
        r=unavailable_capability('보건증 발급을 대신 신청해줘.')
        self.assertIn('실행할 수 없습니다',r['answer']);self.assertNotIn('어떤 업무',r['answer'])
        self.assertEqual(unavailable_capability('현재 공영주차장 자리 수 실시간 조회가 가능한가요?')['degraded_reason'],'live_data_unavailable')

if __name__=='__main__':unittest.main()
