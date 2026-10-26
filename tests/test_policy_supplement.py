from pathlib import Path
from datetime import datetime,timezone
import unittest
from unittest.mock import patch
from chatbot.policy_supplement import POLICY,LOCAL,policy_fields,disability_policy
from chatbot.faq_targets import confident_official_page,collection_guide
from scripts.ingest_official_materials import _official_url

HTML=(Path(__file__).parent/'fixtures/disability_policy_20261026.html').read_text(encoding='utf8')
LOCAL_BODY='''## 제도시책
#### 장애인 연금
지원대상: 장애인연금법상 중증장애인에 해당하는 자
##### 2026년 선정기준액
단독가구 : 140만원
부부가구 : 224만원
#### 장애수당
대상: 18세 이상 장애인연금법상 중증장애인이 아닌 자'''

class PolicySupplementTests(unittest.TestCase):
    def answer(self,q,html=HTML,local=LOCAL_BODY,checked=None):
        now=datetime.now(timezone.utc).isoformat()
        rows=[{'url':POLICY,'raw_html':html,'last_checked_at':checked or now},
              {'url':LOCAL,'content':local,'last_checked_at':now}]
        with patch('database_db.raw_pages.read_raw_pages',return_value=rows):return disability_policy(q,object())

    def test_same_programme_national_age_and_current_local_thresholds(self):
        r=self.answer('장애인연금은 누가 신청할 수 있나요?')
        self.assertIsNotNone(r)
        for t in ('18세 이상의 장애인연금법상 중증','월 말일까지','140만원','224만원','심사 후 결정'):
            self.assertIn(t,r['answer'])
        self.assertEqual({s['url'] for s in r['sources']},{POLICY,LOCAL})

    def test_conflict_expiry_missing_age_or_wrong_year_cannot_supply_eligibility(self):
        self.assertIsNone(self.answer('장애인연금 신청 대상',local=LOCAL_BODY.replace('140만원','138만원')))
        self.assertIsNone(self.answer('장애인연금 신청 대상',checked='2020-01-01T00:00:00Z'))
        self.assertIsNone(self.answer('장애인연금 신청 대상',html=HTML.replace('18세 이상의 장애인연금법상','장애인연금법상')))
        self.assertIsNone(self.answer('장애인연금 신청 대상',html=HTML.replace('2026년','2025년')))
        self.assertIsNone(policy_fields(HTML,2025))

    def test_no_other_programme_personal_or_past_entitlement_shortcut(self):
        for q in ('장애수당 대상','장애인연금과 장애아동수당 대상 비교','17살 장애인연금 신청 대상',
                  '공무원 장애인연금 대상','2025년 장애인연금 신청 대상','작년 장애인연금 신청 대상','장애인연금 지급액 얼마'):
            self.assertIsNone(self.answer(q))

    def test_only_one_registered_external_url_is_accepted_for_refresh(self):
        self.assertTrue(_official_url(POLICY))
        for u in ('https://www.mohw.go.kr/issue/popup/policy_03.html',POLICY+'&evil=1',
                  'https://www.mohw.go.kr.evil.test/menu.es?mid=a10710030100','http://www.mohw.go.kr/menu.es?mid=a10710030100'):
            self.assertFalse(_official_url(u))

    def test_collection_navigation_preserves_free_condition_and_other_subjects(self):
        for q in ('냉장고랑 세탁기 무료 수거 되나요?','모터를 뺀 세탁기도 무료로 가져가요?',
                  '냉장고 무료 방문수거 신청은 어디로 해요?'):
            self.assertEqual(confident_official_page(q),'https://www.saha.go.kr/portal/contents.do?mId=0405050104')
        for q in ('냉장고 수수료 얼마야','냉장고 무료 구입 지원금','자전거랑 냉장고 무료 수거해요?',
                  '무료 냉장고 수거 안 되면 유상 수수료 얼마야'):
            self.assertIsNone(collection_guide(q))

    def test_compound_pickup_word_preserves_method_and_free_exception(self):
        import json
        from chatbot.query_subject import fallback_keywords
        from chatbot.structured_answers import structured_brief
        row=json.loads((Path(__file__).parent/'fixtures/field_completion_sources_20261026.json').read_text(encoding='utf8'))['0405050104']
        for q in ('냉장고 무료 방문수거 신청은 어디로 해요?', '냉장고 무상수거 접수는 어디로 하나요?'):
            words=fallback_keywords(q)
            self.assertIn('수거',words)
            self.assertNotIn('해요',words)
            result=structured_brief(q,{'metadata':{'title':'폐기물','url':row['url']}},row['body'],words)
            self.assertIsNotNone(result)
            self.assertIn('1599-0903',result['answer'])
            self.assertIn('훼손',result['answer'])

if __name__=='__main__':unittest.main()
