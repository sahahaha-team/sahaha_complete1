"""Regressions discovered by the separate wording/rare-question audit."""
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from chatbot.answer_goal import answer_goal
from chatbot.passport_documents import document_request, parse_passport_documents
from chatbot.official_content import official_html_text
from chatbot.structured_answers import structured_brief, field_matches
from chatbot.source_warnings import reviewed_source
from chatbot.source_scope import focus_terms
from chatbot.emergency_guidance import answer_emergency_question
from chatbot.retriever import HybridRetriever, FreshResults
from tests.test_accuracy_followup import doc
from tests.test_passport_documents import HTML


class IndependentFailureTests(unittest.TestCase):
    def test_explicit_requested_items_keep_their_field(self):
        for q,goal in [
            ('주민등록증을 처음 만들 건데 신청 순서가 궁금합니다.','method'),
            ('만17살 아이 여권 재발급을 엄마가 하려면 챙길 것은?','documents'),
            ('금연클리닉에서 주는 약은 하루 몇 알 먹어야 하나요?','medical_details'),
            ('사전컨설팅감사는 소송이 진행 중인 일도 신청 가능한가요?','conditions')]:
            with self.subTest(q=q):self.assertEqual(answer_goal(q),goal)
        self.assertNotIn('순서',focus_terms('주민등록증 신청 순서'))

    def test_take_with_you_is_passport_documents_not_an_online_service(self):
        q='만17살 아이 여권 재발급을 엄마가 하려면 챙길 것은?'
        self.assertTrue(document_request(q))
        answer=parse_passport_documents(q,official_html_text(HTML))
        self.assertIn('법정대리인 동의서',answer)
        self.assertIn('기존 여권',answer)
        self.assertNotIn('정부24',answer)

    def test_online_result_cannot_be_replaced_with_the_first_clinical_visit(self):
        q='보건증 검사는 이미 받았어요. 결과서 인터넷 발급은 어떻게 해요?'
        self.assertFalse(field_matches('method','처리 절차: Step 1. 접수 1층 민원실 접수',q))
        f=json.loads((Path(__file__).parent/'fixtures/online_certificate_20261016.json').read_text(encoding='utf8'))
        body,meta=reviewed_source(f['content'],f)
        r=structured_brief(q,{'content':body,'metadata':meta},body,{'건강진단결과서'})
        self.assertIsNotNone(r)
        self.assertIn('공공보건포털',r['answer'])
        self.assertIn('정상',r['answer'])
        self.assertIn('1년',r['answer'])

    def test_outdated_authentication_and_helpdesk_are_quarantined_without_erasing_the_route(self):
        f=json.loads((Path(__file__).parent/'fixtures/online_certificate_20261016.json').read_text(encoding='utf8'))
        body,meta=reviewed_source(f['content'],f)
        self.assertNotIn('공인인증기관에서 발행한',body)
        self.assertNotIn('1566-7129',body)
        self.assertIn('온라인 발급 : 공공보건포털',body)
        self.assertTrue(meta['source_warning'])

    def test_student_does_not_automatically_prove_a_youth_age_group(self):
        body='## 금연클리닉\n대상 : 금연을 희망하는 지역주민\n기간 : 월-금요일 09:00~18:00 청소년은 예약 필수'
        r=structured_brief('학생인데 금연클리닉에 가려면 먼저 예약해야 해요?',doc(body,'금연클리닉'),body,{'금연','클리닉'})
        self.assertTrue(r['is_clarification'])
        self.assertIn('청소년인가요',r['answer'])

    def test_active_gas_verb_forms_are_immediate_but_negative_and_training_forms_are_not(self):
        for q in ['가스가 새는 것 같아요 구청 문 열 때까지 기다려야 하나요?','집에서 가스가 새요','가스가 샜는데 어디로 연락해요?']:
            self.assertIn('119',answer_emergency_question(q)['answer'])
        for q in ['가스가 새지 않는데 예방교육을 신청하고 싶어요','가스 누출 보험 지원금 문의']:
            self.assertIsNone(answer_emergency_question(q))

    def test_source_lookup_error_is_not_claimed_to_be_an_expired_page(self):
        r=object.__new__(HybridRetriever);r.db=Mock()
        with patch('database_db.raw_pages.read_raw_pages',side_effect=TimeoutError):
            fresh=r.filter_fresh_results('정화조 청소 주기',[doc('내용','정화조')])
        self.assertEqual(fresh,[])
        self.assertTrue(fresh.verification_failed)
        with patch('database_db.raw_pages.read_raw_pages',return_value=[]):
            self.assertFalse(r.filter_fresh_results('정화조 청소 주기',[doc('내용','정화조')]).verification_failed)
        from chatbot.conversation import ChatBot
        bot=object.__new__(ChatBot)
        bot._check_personal_info=Mock(return_value=None)
        bot.contextual_message=Mock(side_effect=lambda _sid,q:q)
        bot._clear_pending_clarification=Mock()
        bot._get_history_safe=Mock(return_value=[])
        bot._save_conversation_safe=Mock()
        bot.retriever=Mock()
        bot.retriever.search.return_value={'results':[doc('내용','정화조')],'degraded':False,'reason':None}
        bot.retriever.filter_fresh_results.return_value=fresh
        bot.retriever.select_grounded_results.return_value=[]
        bot.retriever.assess_evidence.return_value={'confident':False,'top_similarity':0}
        with patch('chatbot.contact_directory.contact_responder.respond',return_value=None), patch('chatbot.passport_documents.answer_passport_documents',return_value=None), patch('chatbot.conversation.answer_verified_table_question',return_value=None):
            answer=bot.chat('fixture-session','정화조 청소 주기 알려줘')
        self.assertEqual(answer['degraded_reason'],'retrieval_error')
        self.assertIn('조회하는 중',answer['answer'])
