import unittest
from unittest.mock import patch

from chatbot.emergency_guidance import answer_emergency_question, FIRE_SOURCE_URL
from chatbot.evidence import assess_evidence, select_grounded_results, topic_support
from chatbot.query_subject import fallback_keywords, normalize_query, subject_query
from chatbot.source_answers import build_source_answer
from chatbot.retriever import HybridRetriever


def doc(title, content, *, bm25=30, similarity=.95):
    return {"content": content, "metadata": {"title": title, "url": "https://www.saha.go.kr/portal/test"},
            "bm25_score": bm25, "similarity": similarity}


class EmergencyRoutingTests(unittest.TestCase):
    def test_actual_reported_question_and_fire_variants(self):
        for query in ("당리동 인근 공장 화제 신고는 어떻게해?", "당리동 공장 화재 신고 전화번호", "공장 불났어 어디 신고해?", "괴정동 뒷산에 불이 났어요", "공장 화재 신고 담당부서 알려줘"):
            with self.subTest(query=query):
                result = answer_emergency_question(query)
                self.assertIn("119", result["answer"])
                self.assertIn("대피", result["answer"])
                self.assertIn("전화를 끊지", result["answer"])
                self.assertEqual(result["sources"][0]["url"], FIRE_SOURCE_URL)
                self.assertNotIn("주정차", result["answer"])

    def test_news_and_fire_admin_queries_are_not_emergency_reporting(self):
        for query in ("화제가 된 사하구 행사 알려줘", "영화제 신고 방법", "공장 설립 신고 방법", "소방시설 안전점검 담당부서", "화재 피해 지원금", "화재 발생 피해 지원금", "불이 난 공장 피해 보상", "화재 발생 건수는 어디서 봐?", "화재 신고 통계 건수", "화재 예방 교육 신청", "불법주차 신고 방법"):
            self.assertIsNone(answer_emergency_question(query), query)

    def test_fire_typo_normalization_has_context(self):
        self.assertIn("화재 신고", normalize_query("공장 화제 신고"))
        self.assertEqual(normalize_query("화제가 된 정책"), "화제가 된 정책")
        self.assertEqual(normalize_query("영화제 신고"), "영화제 신고")

    def test_emergency_route_works_without_contact_file_models_or_database(self):
        from fastapi.testclient import TestClient
        import app
        with patch.object(app, "get_chatbot", side_effect=AssertionError("Heavy services")), patch.object(app.contact_responder, "respond", side_effect=AssertionError("Contact lookup")):
            result = TestClient(app.app).post("/api/chat", json={"message": "당리동 인근 공장 화제 신고는 어떻게해?"})
        self.assertEqual(result.status_code, 200)
        self.assertIn("119", result.json()["answer"])

    def test_emergency_address_never_leaks_or_enters_history(self):
        from fastapi.testclient import TestClient
        import app
        with patch.object(app, "_chatbot") as bot, patch.object(app, "get_chatbot", side_effect=AssertionError("Heavy services")):
            result = TestClient(app.app).post("/api/chat", json={"message": "당리동 123-45 공장에 불이 났어 010-1234-5678로 전화하면돼?"})
        self.assertEqual(result.status_code, 200)
        self.assertIn("119", result.json()["answer"])
        self.assertNotIn("123-45", result.json()["answer"])
        self.assertNotIn("010-1234", result.json()["answer"])
        bot.remember_contact_exchange.assert_not_called()


class SubjectEvidenceTests(unittest.TestCase):
    def test_region_and_generic_report_word_cannot_pass_high_scores(self):
        wrong = doc("불법주정차 단속 안내", "당리동 CCTV 신고 방법")
        for keywords in ({"당리동", "신고"}, {"당리동", "공장", "화재", "신고"}):
            evidence = assess_evidence([wrong], keywords=keywords, domain_intent=True, min_similarity=.45)
            self.assertFalse(evidence["confident"])
            self.assertEqual(select_grounded_results([wrong], keywords=keywords, domain_intent=True, min_similarity=.45), [])

    def test_independent_docs_cannot_lend_each_other_missing_topics(self):
        documents = [doc("공장 등록", "공장 설립 신청"), doc("화재", "화재 안전 교육")]
        self.assertFalse(assess_evidence(documents, keywords={"공장", "화재"}, domain_intent=True, min_similarity=.45)["confident"])

    def test_actual_topic_evidence_still_passes(self):
        result = doc("공장 소음 민원", "공장 소음의 신고와 처리")
        self.assertTrue(topic_support(result, {"공장", "소음", "신고"})[0])

    def test_subject_keywords_remove_location_and_request_language(self):
        self.assertEqual(fallback_keywords("당리동 인근 공장 화제 신고는 어떻게해?"), {"공장", "화재"})
        self.assertEqual(fallback_keywords("여권 신규 발급 준비물 알려줘"), {"여권", "신규"})

    def test_wording_aliases_are_applied_before_morphology(self):
        self.assertEqual(subject_query("불법주차 신고 방법"), "불법주정차 신고 방법")
        self.assertEqual(fallback_keywords("불법주차 신고 방법"), {"불법주정차"})

    def test_parking_report_selects_procedure_not_unrelated_enforcement_faq(self):
        from chatbot.source_answers import focused_section
        text = "단속 FAQ\n주차단속 이의신청 안내\n불법주정차 주민신고제 운영 안내(변경)\n신고방법 : 안전신문고\n신고요건 : 사진 2장"
        passage = focused_section("불법주차 신고 방법", "https://www.saha.go.kr/portal/contents.do?mId=0403080000", text)
        self.assertIn("신고방법", passage)
        self.assertIn("신고요건", passage)
        self.assertNotIn("단속 FAQ", passage)

    def test_unusable_leading_source_does_not_hide_valid_next_source(self):
        class Query:
            def select(self, *_): return self
            def eq(self, _field, url): self.url = url; return self
            def limit(self, *_): return self
            def execute(self):
                body = "불법주정차 안내" if self.url.endswith('wrong') else "공장 소음 신고 방법"
                return type('Result', (), {'data': [{'content': body}]})()
        class Client:
            def table(self, *_): return Query()
        wrong = doc("공장 소음 신고", "공장 소음 신고")
        correct = doc("공장 소음 신고", "공장 소음 신고 방법")
        wrong['metadata']['url'] += 'wrong'
        answer, used = build_source_answer([wrong, correct], Client(), query="공장 소음 신고", topic_keywords={"공장", "소음"})
        self.assertIn("공장 소음 신고 방법", answer)
        self.assertEqual(used, [correct])

    def test_original_and_quoted_body_must_match_not_just_metadata_title(self):
        class Query:
            def select(self, *_): return self
            def eq(self, *_): return self
            def limit(self, *_): return self
            def execute(self): return type("Result", (), {"data": [{"content": "불법주정차 CCTV 신고 방법"}]})()
        class Client:
            def table(self, *_): return Query()
        misleading = doc("화재 신고", "화재 신고는 119")
        self.assertEqual(build_source_answer([misleading], Client(), query="화재 신고", topic_keywords={"화재"}), ("", []))

    def test_generic_bm25_result_cannot_trigger_fast_path(self):
        class Bm25:
            enabled = True
            def search(self, *_args, **_kwargs): return [doc("불법주정차", "당리동 신고", bm25=100)]
        class Vector:
            called = False
            def hybrid_search(self, **_):
                self.called = True
                return []
            def similarity_search(self, *_args, **_kwargs): return []
        retriever = object.__new__(HybridRetriever)
        retriever.bm25, retriever.vs = Bm25(), Vector()
        with patch.object(retriever, "_hybrid_combine", return_value=[]):
            result = retriever.search("당리동 공장 소음 신고 어떻게해?")
        self.assertTrue(retriever.vs.called)
        self.assertEqual(result["results"], [])


if __name__ == "__main__":
    unittest.main()
