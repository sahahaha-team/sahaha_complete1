import json
import unittest
from pathlib import Path
from chatbot.answer_goal import requested_goals
from chatbot.structured_answers import structured_brief, field_matches


class RequestedValueAndConditionScopeTests(unittest.TestCase):
    def source(self, name, key=None):
        data=json.loads((Path(__file__).parent/'fixtures'/name).read_text(encoding='utf8'))
        return data[key] if key else data

    def test_colloquial_access_request_wins_over_incidental_free_word(self):
        query='냉장고 무상수거 접수는 어디로 하나요?'
        self.assertEqual(requested_goals(query), ('method',))
        source=self.source('accuracy_n_sources_20261016.json','free')
        result=structured_brief(query,source,source['content'],{'냉장고','무상수거'})
        self.assertIsNotNone(result)
        self.assertIn('1599-0903',result['answer'])
        self.assertIn('훼손',result['answer'])

    def test_requested_percentage_cannot_use_currency_cap(self):
        query='고향사랑기부 답례품 제공 비율의 상한은 몇 퍼센트인가요?'
        source=self.source('accuracy_n_sources_20261016.json','donation')
        result=structured_brief(query,source,source['content'],{'고향사랑기부'})
        self.assertIsNotNone(result)
        self.assertIn('30%',result['answer'])
        self.assertNotIn('2천만원',result['answer'])
        self.assertFalse(field_matches('cost','연간 최대 2천만원 기부 가능',query))

    def test_conditional_extension_reads_notice_not_filing_method(self):
        source=self.source('accuracy_n_sources_20261016.json','information')
        query='정보공개청구 결정이 연장되면 연장 사유도 문서로 알려주나요?'
        result=structured_brief(query,source,source['content'],{'정보공개청구'})
        self.assertIsNotNone(result)
        self.assertIn('연장사유',result['answer'])
        self.assertIn('문서',result['answer'])
        self.assertNotIn('청구방법',result['answer'])

    def test_expanded_subservice_retains_explicit_provider_exclusions(self):
        source=self.source('accuracy_m_sources_U017.json')
        query='지방세 고충민원이 법원 소송 중이면 신청할 수 없나요?'
        result=structured_brief(query,source,source['content'],{'지방세'})
        self.assertIsNotNone(result)
        self.assertIn('제외대상',result['answer'])
        self.assertIn('소송이 진행 중',result['answer'])

    def test_unrelated_service_cannot_borrow_provider_exclusions(self):
        source=self.source('accuracy_m_sources_U017.json')
        source['content']=source['content'].replace('권리침해된 고충민원','권리침해된 별도민원')
        query='지방세 고충민원이 법원 소송 중이면 신청할 수 없나요?'
        result=structured_brief(query,source,source['content'],{'지방세'})
        self.assertTrue(result is None or '소송이 진행 중' not in result['answer'])


if __name__=='__main__':
    unittest.main()
