import json
import unittest
from pathlib import Path

from chatbot.answer_goal import requested_goals
from chatbot.contact_directory import is_contact_lookup_question
from chatbot.evidence import is_time_compatible, is_service_source
from chatbot.query_subject import fallback_keywords
from chatbot.structured_answers import structured_brief


class ReferenceYearRoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows=json.loads((Path(__file__).resolve().parents[1]/'evaluation/results/accuracy_sources_20261016.json').read_text(encoding='utf-8'))['sources']
        cls.rows={r['title']:r for r in rows}

    def source(self,title):
        row=self.rows[title]
        return {'content':row['body'],'metadata':{'url':row['url'],'title':title,'source_type':'crawled_page'}}

    def test_applicant_event_year_is_not_the_requested_publication_year(self):
        doc=self.source('조상 땅 찾기')
        for year in (2007,2009):
            query=f'조상 땅 찾기에서 {year}년에 사망한 분의 상속인은 어떤 증명서를 챙기나요?'
            self.assertTrue(is_time_compatible(query,doc))
            self.assertEqual(requested_goals(query),('documents',))
            result=structured_brief(query,doc,doc['content'],fallback_keywords(query))
            self.assertIsNotNone(result)
            for term in ['신분증','2008','이전','제적등본','이후','가족관계증명서','기본증명서']:
                self.assertIn(term,result['answer'])
            self.assertNotIn('위임장',result['answer'])
        self.assertTrue(is_time_compatible('2007년 3월 2일에 사망하신 분의 조상 땅 찾기 서류',doc))

    def test_separate_historical_year_and_statistics_still_need_source_evidence(self):
        doc=self.source('조상 땅 찾기')
        for query in ['2007년 조상 땅 찾기 규정', '2007년에 사망한 분의 2025년 당시 신청 규정',
                      '2007년에 사망한 분의 2007년 당시 신청 규정', '2007년 사망 통계 보고서',
                      '2007년 전입 규정', '2007년 입사 제도']:
            self.assertFalse(is_time_compatible(query,doc))

    def test_communication_only_and_number_requests_are_different(self):
        query='마을세무사 상담은 전화만 되는 건가요? 다른 방식도 알려주세요.'
        self.assertFalse(is_contact_lookup_question(query))
        self.assertEqual(requested_goals(query),('method',))
        doc=self.source('마을세무사')
        result=structured_brief(query,doc,doc['content'],fallback_keywords(query))
        for term in ['전화','팩스','이메일','추가상담','시간','장소','대면']:
            self.assertIn(term,result['answer'])
        self.assertTrue(is_contact_lookup_question('마을세무사 전화번호 알려주세요'))
        self.assertTrue(is_contact_lookup_question('여권 전화만 알려줘'))
        self.assertFalse(is_contact_lookup_question('마을세무사 상담은 전화만 되나요?'))

    def test_same_named_program_grant_does_not_become_a_new_service(self):
        query='자격증 응시료 지원금의 최대 한도가 얼마예요?'
        doc=self.source('자격증 등 응시료 지원')
        self.assertEqual(requested_goals(query),('cost',))
        self.assertTrue(is_service_source(query,doc,{'응시료'}))
        self.assertFalse(is_service_source('허구축하금 지원금 얼마',doc,{'응시료'}))
        result=structured_brief(query,doc,doc['content'],{'응시료'})
        self.assertIsNotNone(result)
        self.assertIn('8만원',result['answer'])
        self.assertIn('정기시험',result['answer'])
        self.assertIn('연 1회',result['answer'])
