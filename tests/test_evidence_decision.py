import unittest

from chatbot.evidence_decision import document_decision, assess_documents, unavailable_answer


def source(body, title='보건소', **extra):
    return {'content': body, 'metadata': {'title': title,
        'url': 'https://www.saha.go.kr/health/contents.do?mId=test',
        'source_type': 'crawled_page'}, **extra}


class EvidenceDecisionTests(unittest.TestCase):
    def test_hours_and_location_require_both_actual_fields(self):
        doc = source('## 보건소\n진료시간 : 평일 09:00~18:00\n위치 : 부산광역시 사하구 하신중앙로 185')
        result = document_decision('보건소 진료시간과 위치 알려줘', doc, {'보건소'})
        self.assertEqual(result['decision'], 'supported')
        self.assertEqual(set(result['matched_fields']), {'hours', 'location'})

    def test_missing_location_is_partial_and_not_no_related_source(self):
        doc = source('## 보건소\n진료시간 : 평일 09:00~18:00')
        result = assess_documents('보건소 시간과 위치 알려줘', [doc], {'보건소'})
        self.assertTrue(result['confident'])
        self.assertEqual(result['decision'], 'partial')
        self.assertEqual(result['missing_fields'], ['location'])

    def test_vaccine_eligibility_does_not_establish_place(self):
        doc = source('## 폐렴구균 예방접종\n대상 : 만 65세 이상 지역주민', '폐렴구균 예방접종')
        result = document_decision('폐렴구균 접종 장소 알려줘', doc, {'폐렴구균'})
        self.assertTrue(result['relevant'])
        self.assertNotEqual(result['decision'], 'supported')
        self.assertIn('location', result['missing_fields'])

    def test_high_vector_score_alone_does_not_establish_fire_topic(self):
        doc = source('## 불법주정차\n신고방법 : 안전신문고', '불법주정차', vector_similarity=.99)
        result = document_decision('공장 화재 신고 방법', doc, {'공장','화재'})
        self.assertTrue(result['vector_candidate'])
        self.assertFalse(result['relevant'])

    def test_changed_original_cannot_borrow_old_title(self):
        doc = source('화재 신고 방법', '화재', _raw_page={'content':'## 불법주정차\n신고방법 : 안전신문고'})
        self.assertFalse(document_decision('화재 신고 방법', doc, {'화재'})['relevant'])

    def test_price_without_value_cannot_shortcut_search(self):
        doc = source('## 대형폐기물\n수수료 안내', '대형폐기물')
        self.assertNotEqual(document_decision('대형폐기물 비용 알려줘',doc,{'대형폐기물'})['decision'],'supported')

    def test_source_update_invalidates_cached_field_coverage(self):
        a = source('## 보건소\n진료시간 : 평일 09:00~18:00')
        b = source('## 보건소\n진료시간 확인 필요')
        self.assertEqual(document_decision('보건소 진료시간',a,{'보건소'})['decision'],'supported')
        self.assertNotEqual(document_decision('보건소 진료시간',b,{'보건소'})['decision'],'supported')

    def test_private_or_other_district_source_never_establishes_answer(self):
        doc = source('## 보건소\n진료시간 : 평일 09:00~18:00')
        doc['metadata']['url'] = 'https://example.test/health'
        self.assertFalse(document_decision('보건소 진료시간',doc,{'보건소'})['relevant'])

    def test_related_documents_do_not_combine_different_subjects_to_pass(self):
        rows=[source('## 공장\n신청방법 : 방문', '공장'),source('## 화재\n교육장소 : 구청', '화재')]
        self.assertFalse(assess_documents('공장 화재 신고 방법',rows,{'공장','화재'})['confident'])

    def test_lookup_failure_does_not_claim_that_service_does_not_exist(self):
        result=unavailable_answer('retrieval_error')
        self.assertIn('조회하는 중',result['answer'])
        self.assertNotIn('존재하지',result['answer'])
        self.assertEqual(result['evidence']['decision'],'unavailable')


if __name__ == '__main__':
    unittest.main()
