import json
import unittest
from pathlib import Path
from chatbot.contact_directory import ContactDirectoryResponder, is_contact_lookup_question
from chatbot.structured_answers import structured_brief, field_matches


class PaymentAndCommunicationIntentTests(unittest.TestCase):
    @staticmethod
    def source(file, key):
        data = json.loads((Path(__file__).parent/'fixtures'/file).read_text(encoding='utf8'))
        return data[key]

    def test_communication_alternatives_skip_employee_number_lookup(self):
        responder = ContactDirectoryResponder(Path('not-an-existing-contact-file.json'))
        for query in ('마을세무사 상담 방법은 전화 외에도 있나요?', '세무 상담은 전화 말고 다른 방법도 있나요?',
                      '상담을 팩스 대신 이메일로 할 수 있는 방법 알려줘'):
            self.assertIsNone(responder.respond('test', query))
            self.assertFalse(is_contact_lookup_question(query))

    def test_explicit_number_still_uses_contact_lookup(self):
        self.assertTrue(is_contact_lookup_question('마을세무사 담당부서 전화번호 알려줘'))
        self.assertIsNotNone(ContactDirectoryResponder(Path('not-an-existing-contact-file.json')).respond(
            'test','전화 상담 방법이랑 담당부서 전화번호 알려줘'))

    def test_actual_payment_mode_is_not_an_eligibility_question(self):
        source = self.source('accuracy_p_sources_20261016.json', 'birth')
        query = '첫만남이용권 지급은 국민행복카드 포인트로 받나요?'
        result = structured_brief(query, source, source['content'], {'첫만남이용권'})
        self.assertIsNotNone(result)
        self.assertIn('국민행복카드', result['answer'])
        self.assertIn('포인트', result['answer'])
        self.assertNotIn('확인되지', result['answer'])

    def test_negated_free_service_is_a_real_exclusion(self):
        query = '부품 탈취된 냉장고는 무상수거 제외 품목인가요?'
        self.assertTrue(field_matches('conditions', '※ 부품 탈취 등 원형훼손 제품은 무상 수거가 되지 않음.', query))
        self.assertFalse(field_matches('conditions', '신청방법: 홈페이지에서 제외품목 확인', query))

    def test_amount_field_does_not_produce_false_unknown_detail(self):
        source = self.source('accuracy_n_sources_20261016.json', 'donation')
        result = structured_brief('고향사랑기부금 답례품은 기부금액의 몇 퍼센트 이내예요?',
                                  source, source['content'], {'고향사랑기부'})
        self.assertIsNotNone(result)
        self.assertIn('30%', result['answer'])
        self.assertNotIn('확인되지', result['answer'])


if __name__ == '__main__':
    unittest.main()
