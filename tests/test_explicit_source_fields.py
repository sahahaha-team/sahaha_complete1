import json
import unittest
from pathlib import Path
from chatbot.structured_answers import structured_brief, field_matches
from chatbot.query_subject import fallback_keywords
from chatbot.reference_answers import reference_answer


class ExplicitSourceFieldTests(unittest.TestCase):
    def source(self, name, key=None):
        d=json.loads((Path(__file__).parent/'fixtures'/name).read_text(encoding='utf8'))
        return d[key] if key else d

    def test_completed_certificate_print_request_keeps_existing_document(self):
        d=self.source('accuracy_t_certificate_20261016.json')
        q='검사를 끝낸 보건증을 인터넷에서 출력하는 방법이 궁금해요.'
        result=structured_brief(q,d,d['content'],fallback_keywords(q))
        self.assertIsNotNone(result)
        self.assertIn('공공보건포털',result['answer'])
        self.assertIn('정상',result['answer'])
        self.assertIn('1년',result['answer'])

    def test_age_question_can_read_explicit_official_screening_criterion(self):
        d=self.source('accuracy_o_sources_20261016.json','id')
        q='주민등록증 신규 발급은 만 몇 세가 대상인가요?'
        result=structured_brief(q,d,d['content'],{'주민등록증'})
        self.assertIsNotNone(result)
        self.assertIn('17세 이상 확인',result['answer'])
        self.assertFalse(field_matches('eligibility','구비서류: 17세 이상의 동일 세대원과 동행',q))

    def test_excluded_audience_is_not_a_second_general_audience_request(self):
        d=self.source('accuracy_m_sources_U017.json')
        q='납세자보호관 고충민원 신청 제외대상에 소송 중인 것도 포함되나요?'
        result=structured_brief(q,d,d['content'],{'납세자보호관'})
        self.assertIsNotNone(result)
        self.assertIn('소송이 진행 중',result['answer'])
        self.assertNotIn('확인되지',result['answer'])

    def test_page_link_does_not_claim_an_unverified_pdf(self):
        body='작은도서관 안내'
        d={'content':body,'metadata':{'title':'작은도서관','url':'https://www.saha.go.kr/portal/contents.do?mId=0408030000','source_type':'crawled_page','attachments':[]}}
        q='사하구 도서관 안내 PDF 첨부파일 링크를 주세요.'
        result=reference_answer(q,d,body,{'도서관'})
        self.assertIsNotNone(result)
        self.assertIn('PDF 첨부파일은 현재 확인한 자료에 없습니다',result['answer'])
        self.assertTrue(result['degraded'])
        d['metadata']['attachments']=[{'name':'다른 형식 안내(HWP)','url':'https://www.saha.go.kr/guide.hwp'}]
        result=reference_answer(q,d,body,{'도서관'})
        self.assertNotIn('guide.hwp',result['answer'])
        self.assertTrue(result['degraded'])


if __name__=='__main__':
    unittest.main()
