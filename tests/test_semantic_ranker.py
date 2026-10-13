import unittest
from unittest.mock import patch

from config import RAG_RERANK_MODEL
from chatbot.semantic_ranker import SemanticRanker, text_hash, source_hash, semantic_keywords, has_semantic_support, passages
from chatbot.evidence_decision import document_decision, source_body
from chatbot.grounded_planner import answer_with_grounded_model
from chatbot.source_scope import normalize_plain_source
from chatbot.answer_goal import answer_goal, requested_goals
from chatbot.structured_answers import field_matches


def source(body, title='금연'):
    return {'content': body, 'metadata': {'title': title,
        'url': 'https://www.saha.go.kr/health/contents.do?mId=test', 'source_type': 'crawled_page'}}


def bound(query, doc, terms=('금연',), logit=1, margin=3):
    return {**doc, '_semantic_support': {'model': RAG_RERANK_MODEL,
        'query_hash': text_hash(query), 'source_hash': source_hash(doc),
        'terms': list(terms), 'logit': logit, 'margin': margin}}


class SemanticRankerTests(unittest.TestCase):
    def test_synonym_binding_can_establish_topic_but_not_missing_field(self):
        query='담배를 끊고 싶은데 어디서 상담해요?'
        doc=bound(query,source('## 금연\n대상 : 금연을 희망하는 지역주민'))
        result=document_decision(query,doc,{'담배','상담'})
        self.assertTrue(result['relevant'])
        self.assertNotEqual(result['decision'],'supported')
        self.assertIn('location',result['missing_fields'])

    def test_changed_question_or_source_invalidates_binding(self):
        query='담배를 끊고 싶어요'
        doc=bound(query,source('## 금연\n내용 : 금연 상담'))
        self.assertTrue(has_semantic_support(query,doc))
        self.assertFalse(has_semantic_support('술을 끊고 싶어요',doc))
        self.assertFalse(has_semantic_support(query,{**doc,'content':'세금 납부 안내'}))
        self.assertFalse(has_semantic_support(query,{**doc,'_raw_page':{'content':'새로운 안내'}}))
        self.assertFalse(has_semantic_support(query,{**doc,'metadata':{**doc['metadata'],'title':'다른 사업'}}))

    def test_low_logit_or_small_margin_does_not_bypass_topic(self):
        for score,margin in [(-10,4),(3,.2)]:
            doc=bound('질문',source('금연 상담'),logit=score,margin=margin)
            self.assertEqual(semantic_keywords('질문',doc,{'원래'}),{'원래'})

    def test_official_and_district_guards_remain_with_semantic_binding(self):
        query='부산진구 보건소 진료시간'
        doc=bound(query,source('## 보건소\n진료시간 : 09:00~18:00','보건소'),terms=('보건소',))
        self.assertFalse(document_decision(query,doc,{'보건소'})['relevant'])
        doc['metadata']['url']='https://example.com'
        self.assertFalse(document_decision(query,doc,{'보건소'})['relevant'])

    def test_explicit_service_contradiction_is_not_overridden(self):
        query='폐렴구균 접종 장소 알려줘'
        doc=bound(query,source('## 임산부\n장소 : 보건소 1층','임산부'),terms=('임산부',))
        self.assertFalse(document_decision(query,doc,{'폐렴구균'})['relevant'])

    def test_missing_local_model_preserves_existing_candidates(self):
        ranker=SemanticRanker();rows=[source('금연 상담')]
        with patch.object(ranker,'_load',return_value=False):
            result,info=ranker.rerank('금연',rows,{'금연'})
        self.assertEqual(result,rows)
        self.assertFalse(info['used'])

    def test_passage_never_borrows_changed_vector_chunk(self):
        doc=source('현재 공식 안내 내용입니다.')
        doc['_match_content']='오래된 약품명과 복용량'
        self.assertNotIn('오래된',' '.join(passages('약품명',doc,{'약품명'})))

    def test_packet_keywords_cannot_leak_to_another_source(self):
        query='담배 끊는 상담 내용 알려줘'
        first={'document':source('','금연'),'body':'','section_body':'','keywords':{'금연'},'units':[]}
        second={'document':source('','납세'),'body':'','section_body':'','keywords':{'담배','상담'},'units':[]}
        seen=[]
        def brief(q,d,b,k):
            seen.append(k)
            return {'answer':'검사','documents':[d],'is_clarification':False} if len(seen)==2 else None
        with patch('chatbot.grounded_planner.prepare_evidence',return_value=[first,second]), \
             patch('chatbot.grounded_planner.reference_answer',return_value=None), \
             patch('chatbot.structured_answers.structured_brief',side_effect=brief):
            answer_with_grounded_model(query,[],None,{'원래'},None)
        self.assertEqual(seen,[{'금연'},{'담배','상담'}])

    def test_field_heading_labels_value_without_changing_owner(self):
        body=normalize_plain_source('## 금연\n### 운영시간\n평일 09:00~18:00\n## 다른 사업\n대상 : 어린이','금연')
        self.assertIn('운영시간: 평일 09:00~18:00',body)
        self.assertIn('## 다른 사업',body)

    def test_weekday_reservation_period_is_a_schedule(self):
        self.assertTrue(field_matches('schedule','예약기간 : 매주 일요일~수요일 ▷ 다음주 월요일~일요일 예약','며칠 전에 예약해요?'))

    def test_generic_title_requires_an_opening_fact_about_requested_subject(self):
        from chatbot.evidence import is_service_source
        doc=source('## 설치안내\n간판은 허가를 받은 후 표시해야 합니다. 표시기간은 3년이며 계속 표시하려면 연장허가를 받아야 합니다.','설치안내')
        self.assertTrue(is_service_source('간판 갱신 기간',doc,{'간판'}))
        doc['content']='## 임산부 지원\n구비서류 : 주민등록등본\n지원기간 : 1년'
        self.assertFalse(is_service_source('주민등록등본 발급 기간',doc,{'주민등록등본'}))

    def test_field_heading_cannot_narrow_a_different_requested_field(self):
        from chatbot.source_scope import detail_section_bounds
        units=['## 간판 안내','표시기간 : 3년','### 연장허가 구비서류','신청서 : 1부']
        self.assertIsNone(detail_section_bounds('간판을 갱신해야 하나요?',units))

    def test_official_example_markers_do_not_drop_the_exclusion_row(self):
        from chatbot.answer_completion import source_unit_complete
        self.assertTrue(source_unit_complete('음식물 — 제외품목: 육류 : 예) 동물의 뼈, 조개류의 껍질'))

    def test_waste_pickup_is_not_a_document_request(self):
        query='망가진 냉장고를 집으로 와서 가져가 주는 서비스가 있어요?'
        self.assertNotEqual(answer_goal(query),'documents')
        self.assertNotIn('documents',requested_goals(query))

    def test_general_clinic_audience_is_not_drug_dosage_evidence(self):
        query='금연클리닉에서 어떤 약을 처방하는지 이름과 복용량 알려줘'
        self.assertEqual(answer_goal(query),'medical_details')
        self.assertFalse(field_matches('medical_details','대상 : 금연을 희망하는 지역주민',query))


class SemanticSafetyTests(unittest.TestCase):
    def test_known_subject_filters_bus_before_bicycle_reranking(self):
        from chatbot.semantic_ranker import eligible_candidates
        bicycle=source('## 자전거 도로\n자전거 도로 현황도를 확인하세요.','자전거 도로')
        bus=source('## 대중교통\n버스 경유지 : 장림시장 - 동아대','대중교통')
        self.assertEqual(eligible_candidates('자전거 지도 어디서 확인해?', [bus,bicycle], {'자전거'}),[bicycle])

    def test_bicycle_mention_in_parking_rule_is_not_a_bicycle_map(self):
        from chatbot.evidence import is_service_source
        doc=source('## 불법주정차\n단속대상 : 자전거 도로에 주차한 자동차','불법주정차')
        self.assertFalse(is_service_source('자전거길 노선 지도 어디에서 볼 수 있어요?',doc,{'자전거','도로'}))

    def test_reference_field_words_do_not_hide_bicycle_topic(self):
        from chatbot.query_subject import query_keywords
        keys=query_keywords('자전거길 공식 노선 지도는 어디에서 볼 수 있나요?', ['자전거','노선','지도','페이지'])
        self.assertEqual(keys,{'자전거도로'})
        self.assertEqual(query_keywords('자전거길 공식 노선 지도는 어디에서 볼 수 있나요?',
            ['자전거','길','공식','노선','지도','페이지']),{'자전거도로'})

    def test_general_health_hours_reject_infant_provider_list(self):
        from chatbot.evidence import is_answerable_document
        doc=source('## 영유아 건강검진\n주소 : 부산 사하구 낙동대로 234','영유아 건강검진')
        self.assertFalse(is_answerable_document('보건소 진료시간이랑 주소 알려줘',doc))

    def test_colloquial_age_reply_keeps_passport_and_parent_role(self):
        from chatbot.response_helpers import build_clarification, resolve_clarification_reply
        from chatbot.passport_documents import applicant_age, applicant_role
        question='고등학생 여권 준비물 알려줘'
        pending={**build_clarification(question),'query':question}
        resolved=resolve_clarification_reply('17살이고 엄마가 신청할 거야',pending)
        self.assertIn('여권',resolved)
        self.assertEqual(applicant_age(resolved),'minor')
        self.assertEqual(applicant_role(resolved),'parent')

    def test_fee_connective_is_not_a_location_request(self):
        from chatbot.question_intent import asks_location
        self.assertFalse(asks_location('마을세무사 상담을 받는 데 돈이 들어요?'))

    def test_semantic_topic_remains_bicycle_not_bus(self):
        from chatbot.evidence_decision import document_decision
        query='자전거 도로 지도 볼 수 있는 공식 페이지 알려줘'
        doc=bound(query,source('## 대중교통\n경유지 : 장림시장 - 동아대','대중교통'),terms=('자전거',))
        self.assertFalse(document_decision(query,doc,{'자전거'})['relevant'])
        self.assertEqual(answer_goal(query),'reference')

    def test_incidental_facility_mention_cannot_replace_requested_owner(self):
        from chatbot.evidence import is_service_source
        doc=source('## 치매 관리\n내용 : 치매 상담\n참고 : 마을건강센터에도 문의 가능','치매 관리')
        self.assertFalse(is_service_source('마을건강센터 건강 상담 알려줘',doc,{'건강'}))

    def test_configured_timeout_is_passed_to_ollama_http_client(self):
        from chatbot.conversation import ChatBot
        from config import OLLAMA_TIMEOUT
        with patch('chatbot.conversation.HybridRetriever'), patch('chatbot.conversation.PERSIST_CONVERSATIONS',False):
            bot=ChatBot()
        self.assertEqual(bot.llm.client_kwargs.get('timeout'),OLLAMA_TIMEOUT)
        self.assertEqual(bot.llm._client._client.timeout.read,OLLAMA_TIMEOUT)

    def test_pdf_carried_over_clause_is_not_an_answer(self):
        from chatbot.answer_completion import source_unit_complete
        self.assertFalse(source_unit_complete('며, 2025년 처리건수 253건'))

    def test_semantics_cannot_replace_nonexistent_named_grant(self):
        query='사하구청 우주여행 지원금 300만원을 신청하려면 어떻게 하나요?'
        doc=bound(query,source('## 출산지원금\n신청방법 : 행정복지센터','출산지원금'),terms=('출산지원금',))
        self.assertFalse(document_decision(query,doc,{'우주여행','지원금'})['relevant'])

    def test_named_village_center_is_not_dementia_center(self):
        from chatbot.evidence import is_service_source
        doc=source('## 치매안심센터\n내용 : 치매 상담','치매안심센터')
        self.assertFalse(is_service_source('당리동 마을건강센터 상담 안내',doc,{'건강','상담'}))

    def test_shared_document_question_does_not_select_maternity_aid(self):
        from chatbot.evidence import is_service_source
        q='행정기관끼리 제 서류를 확인할 수 있으면 제출을 생략할 수 있나요?'
        self.assertEqual(answer_goal(q),'necessity')
        self.assertFalse(is_service_source(q,source('서류 제출 생략 가능','고위험 임산부 의료비지원'),{'서류'}))

    def test_explicit_reservation_need_and_natural_fee_questions_have_fields(self):
        self.assertEqual(answer_goal('무료 법률상담을 받으려면 먼저 예약해야 해요?'),'conditions')
        self.assertEqual(answer_goal('마을세무사 세금 상담은 돈이 들어요?'),'cost')
        self.assertEqual(answer_goal('수강료와 재료비가 같아요?'),'cost')

    def test_compound_fallback_cannot_silently_omit_requested_cost(self):
        from chatbot.concise_answers import concise_source_answer
        doc=source('## 응시료 지원\n신청방법 : 공식 홈페이지에 신청서 제출','응시료 지원')
        result=concise_source_answer('응시료 지원은 얼마나 주고 어떻게 신청해요?',
            '> ## 응시료 지원\n> 신청방법 : 공식 홈페이지에 신청서 제출',[doc],{'응시료','지원'})
        self.assertTrue(result.get('degraded'))
        self.assertIn('비용',result['answer'])


if __name__ == '__main__':
    unittest.main()
