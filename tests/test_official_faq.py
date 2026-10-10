import json
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from chatbot.official_faq import OfficialFAQIndex, PRIORITY_SERVICE_PATH
from chatbot.retriever import HybridRetriever
from chatbot.response_helpers import build_clarification
from crawler.saha_crawler import SahaCrawler
from processor.data_cleaner import DataCleaner


ROOT = Path(__file__).resolve().parent.parent


class OfficialFaqTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = OfficialFAQIndex(ROOT / "resources" / "official_faq.json")
        cls.priority = OfficialFAQIndex(PRIORITY_SERVICE_PATH)

    def test_all_100_official_questions_match_their_approved_answer(self):
        self.assertEqual(len(self.index), 100)
        for item in self.index.items:
            match = self.index.find_best(item["question"], min_score=0.88)
            self.assertIsNotNone(match, item["id"])
            self.assertEqual(match["id"], item["id"])
            self.assertEqual(match["answer"], item["answer"])
            self.assertEqual(match["url"], item["url"])

    def test_every_official_question_has_unique_source_url(self):
        urls = [item["url"] for item in self.index.items]
        self.assertEqual(len(urls), 100)
        self.assertEqual(len(set(urls)), 100)

    def test_priority_variants_match_expected_official_questions(self):
        cases = {
            "구청 대표 번호 뭐야?": 2,
            "주민세 사업소분하고 종업원분 온라인 신고 돼요?": 15,
            "대형 쓰레기 버리는 법 알려줘": 16,
            "보건소 몇 시에 열어요?": 36,
            "성인 예방접종 시간 알려줘": 39,
        }
        for question, expected_id in cases.items():
            match = self.index.find_best(question)
            self.assertIsNotNone(match, question)
            self.assertEqual(match["id"], expected_id, question)

    def test_broad_health_word_is_not_a_direct_official_answer(self):
        self.assertIsNone(self.index.find_best("보건소", min_score=0.65))

    def test_location_and_contact_query_retrieves_both_official_answers(self):
        docs = self.index.search_documents(
            "사하구청 위치와 연락처 알려줘", limit=5, min_score=0.58
        )
        ids = [doc["id"] for doc in docs]
        self.assertEqual(ids[:2], ["official-faq:1", "official-faq:2"])
        context = "\n".join(doc["content"] for doc in docs[:2])
        self.assertIn("낙동대로398번길 12", context)
        self.assertIn("051-220-4000", context)

    def test_official_faq_source_does_not_inherit_unrelated_staff_contact(self):
        retriever = object.__new__(HybridRetriever)
        retriever.official_faq = self.index
        docs = self.index.search_documents(
            "사하구청 위치와 연락처 알려줘", limit=5, min_score=0.58
        )
        _, sources = retriever.format_context("사하구청 위치와 연락처 알려줘", docs)
        self.assertEqual(len(sources), 2)
        self.assertTrue(all(not source["department"] for source in sources))
        self.assertTrue(all(not source["contact"] for source in sources))

    def test_resource_contains_no_missing_answer_or_url(self):
        data = json.loads((ROOT / "resources" / "official_faq.json").read_text(encoding="utf-8"))
        self.assertTrue(all(row.get("answer") and row.get("url") for row in data))

    def test_priority_service_variants_match_verified_sources(self):
        cases = {
            "일반쓰레기 음식물쓰레기 재활용품의 요일별 배출 방법 알려줘": (1001, "0405050000"),
            "소방특화 들락날락 체험은 어떻게 예약해?": (1002, "1207000000"),
            "작은도서관 교육 프로그램 예약 방법 알려줘": (1003, "0408030000"),
            "사하구보건소 몇 시에 문 열어?": (1004, "0103000000"),
            "성인 예방접종은 언제 받을 수 있어?": (1005, "0203020000"),
        }
        for question, (expected_id, url_part) in cases.items():
            match = self.priority.find_best(question, min_score=0.82)
            self.assertIsNotNone(match, question)
            self.assertEqual(match["id"], expected_id, question)
            self.assertIn(url_part, match["url"])


class StructuredHtmlTests(unittest.TestCase):
    def test_heading_and_table_relationship_are_preserved(self):
        crawler = object.__new__(SahaCrawler)
        soup = BeautifulSoup(
            """
            <main>
              <h2>성인 예방접종</h2>
              <p>접종 대상별 시간이 다릅니다.</p>
              <table><tr><th>구분</th><th>시간</th></tr>
              <tr><td>오전</td><td>09:00~11:30</td></tr></table>
            </main>
            """,
            "html.parser",
        )
        content = crawler._extract_content(soup, "https://www.saha.go.kr/health/test")
        self.assertIn("## 성인 예방접종", content)
        self.assertIn("표 | 오전 | 09:00~11:30", content)

        cleaner = DataCleaner()
        cleaned = cleaner.clean_text(content)
        chunks = cleaner.split_structured_text(cleaned)
        self.assertTrue(any("문서 위치: 성인 예방접종" in chunk for chunk in chunks))
        self.assertTrue(any("09:00~11:30" in chunk for chunk in chunks))


class DomainClarificationTests(unittest.TestCase):
    def test_generic_waste_question_answers_before_clarifying(self):
        self.assertIsNone(build_clarification("쓰레기 배출 알려줘"))

    def test_specific_food_waste_question_does_not_repeat_clarification(self):
        self.assertIsNone(build_clarification("음식물쓰레기는 물기를 빼야 하나요?"))

    def test_generic_reservation_question_asks_for_the_actual_program(self):
        self.assertIsNotNone(build_clarification("예약하고 싶어요"))

    def test_generic_health_question_answers_before_clarifying(self):
        self.assertIsNone(build_clarification("보건소 이용하고 싶어요"))

    def test_generic_contact_question_asks_for_duty(self):
        result = build_clarification("담당자 전화번호 알려줘")
        self.assertIsNotNone(result)
        self.assertIn("어떤 민원이나 업무", result["answer"])

    def test_office_location_and_contact_does_not_ask_for_duty(self):
        self.assertIsNone(build_clarification("사하구청 위치와 연락처 알려줘"))

    def test_broad_welfare_question_preserves_user_scope_policy(self):
        result = build_clarification("복지 지원 알려줘")
        self.assertIsNotNone(result)
        self.assertIn("?", result["answer"])

    def test_specific_welfare_question_skips_clarification(self):
        self.assertIsNone(build_clarification("한부모가족 지원 알려줘"))

    def test_broad_tax_question_answers_with_overview(self):
        self.assertIsNone(build_clarification("세금 안내해줘"))


if __name__ == "__main__":
    unittest.main()
