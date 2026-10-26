import json
from pathlib import Path
import unittest
from chatbot.structured_answers import structured_brief, explicit_table_answer, requested_programme_targets
from chatbot.concise_answers import _source_units
from chatbot.verified_facts import parse_disposal_schedule

SOURCES=json.loads((Path(__file__).parent/'fixtures/field_completion_sources_20261026.json').read_text(encoding='utf8'))
def brief(mid,query,keywords):
    row=SOURCES[mid]
    return structured_brief(query,{'metadata':{'title':row['body'].splitlines()[0].lstrip('# '),'url':row['url']}},row['body'],keywords)

class FieldCompletionTests(unittest.TestCase):
    def test_weekdays_keep_actual_disposal_and_collection_times_separate(self):
        answer=parse_disposal_schedule(SOURCES['0405050101']['content'],'요일별 쓰레기 배출 방법')
        self.assertIsNotNone(answer)
        self.assertIn('당일 저녁 7시부터 10시까지',answer)
        self.assertIn('수거는 밤 10시부터 익일 오전 6시까지',answer)
        self.assertIn('배출 금지',answer)

    def test_multiple_appliances_and_original_damage_exception_are_kept(self):
        query='냉장고나 세탁기 같은 대형 폐가전은 무료로 수거해 주나요?'
        r=brief('0405050104',query,{'냉장고','세탁기','무상'})
        self.assertIsNotNone(r)
        for term in ('냉장고','세탁기','온도교환','일반 전기','원형훼손','되지 않음'):
            self.assertIn(term,r['answer'])
        units=_source_units(SOURCES['0405050104']['body'].splitlines())
        self.assertIsNone(explicit_table_answer('훼손된 세탁기 무료 수거',units,'폐기물'))

    def test_both_medical_programmes_keep_their_own_targets(self):
        query='미숙아나 선천성이상아의 의료비 지원을 받을 수 있나요?'
        r=brief('0402030000',query,{'미숙아'})
        self.assertIsNotNone(r)
        lines=r['answer'].splitlines()
        premature=next(x for x in lines if '미숙아 의료비 지원' in x)
        congenital=next(x for x in lines if '선천성이상아 의료비 지원' in x)
        self.assertIn('24시간',premature)
        self.assertIn('37주',premature)
        self.assertIn('2,500',premature)
        self.assertIn('Q코드',congenital)
        self.assertIn('2년',congenital)
        self.assertNotIn('Q코드',premature)
        self.assertEqual(requested_programme_targets('미숙아 의료비 지원 대상',_source_units(SOURCES['0402030000']['body'].splitlines())),[])

    def test_generic_patient_word_cannot_erase_age_and_other_insurance_groups(self):
        r=brief('0406030000','소아암 환자의 의료비 지원제도가 있나요?',{'소아암','암환자','의료비'})
        self.assertIsNotNone(r)
        for term in ('18세 미만','의료급여','차상위','건강보험','소득','재산'):
            self.assertIn(term,r['answer'])

if __name__=='__main__':unittest.main()
