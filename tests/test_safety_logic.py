import unittest

from bs4 import BeautifulSoup

from chatbot.response_helpers import (
    build_clarification,
    build_contextual_search_query,
    build_suggested_questions,
    is_obviously_out_of_domain,
)
from chatbot.evidence import assess_evidence, select_grounded_results
from chatbot.privacy import detect_personal_info, mask_personal_info
from processor.metadata_defaults import fallback_keywords
from processor.metadata_tagger import ensure_metadata
from chatbot.dept_directory import extract_explicit_department
from crawler.saha_crawler import SahaCrawler
from processor.data_cleaner import is_non_page_url
from chatbot.retriever import HybridRetriever


def document(*, title="정보", content="", url="https://www.saha.go.kr/portal/test", similarity=0.7, bm25=0.0):
    return {
        "id": title,
        "content": content,
        "metadata": {"title": title, "url": url, "category": "전자민원"},
        "similarity": similarity,
        "vector_similarity": similarity,
        "bm25_score": bm25,
    }


class EvidenceGateTests(unittest.TestCase):
    def test_out_of_domain_is_blocked_even_with_high_vector_similarity(self):
        results = [document(title="사하구 소개", content="사하구 행정 안내", similarity=0.91)]
        evidence = assess_evidence(results, keywords={"아이폰", "가격"}, domain_intent=False, min_similarity=0.45)
        self.assertFalse(evidence["confident"])
        self.assertEqual(evidence["status"], "insufficient")

    def test_official_lexical_evidence_is_accepted(self):
        results = [document(title="대형폐기물 배출", content="대형 폐기물 배출 신청 방법", similarity=0.53)]
        evidence = assess_evidence(results, keywords={"대형", "폐기물", "배출"}, domain_intent=True, min_similarity=0.45)
        self.assertTrue(evidence["confident"])
        self.assertEqual(evidence["status"], "official")

    def test_clear_admin_intent_can_use_semantic_evidence(self):
        results = [document(title="온라인 처리 안내", content="필요한 절차와 준비사항", similarity=0.62)]
        evidence = assess_evidence(results, keywords={"민원", "신청"}, domain_intent=True, min_similarity=0.45)
        self.assertTrue(evidence["confident"])
        self.assertEqual(evidence["status"], "supported")

    def test_non_official_source_is_never_accepted(self):
        results = [document(title="등본 발급", content="등본 발급 방법", url="https://example.com", similarity=0.99)]
        evidence = assess_evidence(results, keywords={"등본", "발급"}, domain_intent=True, min_similarity=0.45)
        self.assertFalse(evidence["confident"])

    def test_non_official_high_score_cannot_lend_support_to_official_document(self):
        unofficial = document(
            title="아이폰 가격", content="아이폰 가격 정보", url="https://example.com",
            similarity=0.99, bm25=5.0,
        )
        official = document(title="사하구 연혁", content="사하구 역사", similarity=0.4)
        evidence = assess_evidence(
            [unofficial, official], keywords={"아이폰", "가격"},
            domain_intent=False, min_similarity=0.45,
        )
        self.assertFalse(evidence["confident"])

    def test_grounded_selection_excludes_unmatched_documents(self):
        matched = document(title="재활용 안내", content="재활용품 분리배출 방법", bm25=2.0)
        unrelated = document(title="구청 연혁", content="사하구의 역사")
        selected = select_grounded_results(
            [unrelated, matched], keywords={"재활용", "분리배출"},
            domain_intent=True, min_similarity=0.45,
        )
        self.assertEqual([row["id"] for row in selected], [matched["id"]])


class ConversationUxTests(unittest.TestCase):
    def test_obvious_financial_prediction_is_blocked_before_retrieval(self):
        self.assertTrue(is_obviously_out_of_domain("오늘 삼성전자 주가를 예측해줘"))
        self.assertFalse(is_obviously_out_of_domain("사하구 지방세 납부 방법 알려줘"))

    def test_vague_service_request_answers_before_clarifying(self):
        self.assertIsNone(build_clarification("지원받고 싶어요"))

    def test_specific_request_does_not_trigger_clarification(self):
        self.assertIsNone(build_clarification("장애인 복지 지원 신청 방법 알려줘"))

    def test_bed_fee_requires_size_clarification(self):
        result = build_clarification("침대 배출 수수료가 얼마야?")
        self.assertIsNotNone(result)
        self.assertIn("종류와 규격", result["answer"])
        self.assertEqual(len(result["suggested_questions"]), 3)

    def test_bed_fee_with_specific_size_does_not_clarify(self):
        self.assertIsNone(build_clarification("일반침대 2인용 수수료가 얼마야?"))

    def test_follow_up_questions_are_deduplicated_and_limited(self):
        sources = [{"department": "복지정책과", "attachments": [{"name": "신청서", "url": "https://example"}]}]
        questions = build_suggested_questions("복지 지원 알려줘", sources)
        self.assertLessEqual(len(questions), 3)
        self.assertEqual(len(questions), len(set(questions)))

    def test_follow_up_search_keeps_recent_user_context(self):
        history = [
            {"role": "user", "content": "대형 폐기물 배출 방법 알려줘"},
            {"role": "assistant", "content": "종류를 알려주세요"},
        ]
        query = build_contextual_search_query("침대는요?", history)
        self.assertIn("대형 폐기물", query)
        self.assertTrue(query.endswith("침대는요?"))

    def test_new_complete_question_drops_previous_topic(self):
        history = [
            {"role": "user", "content": "기초생활수급자 민원 수수료 면제 알려줘"},
            {"role": "assistant", "content": "면제 대상을 안내해드렸습니다"},
        ]
        question = "주민세 사업소분이나 종업원분은 인터넷으로 신고할 수 있나요?"
        self.assertEqual(build_contextual_search_query(question, history), question)


class PrivacyTests(unittest.TestCase):
    def test_sensitive_input_is_detected_before_storage(self):
        self.assertIsNotNone(detect_personal_info("주민번호 901010-1234567", use_ner=False))
        self.assertIsNotNone(detect_personal_info("메일 hong@example.com", use_ner=False))

    def test_sensitive_output_is_masked(self):
        masked, found = mask_personal_info("연락처는 010-1234-5678입니다", use_ner=False)
        self.assertIn("[MASKED:", masked)
        self.assertTrue(found)

class MetadataFallbackTests(unittest.TestCase):
    def test_keywords_are_generated_without_llm(self):
        keywords = fallback_keywords("대형 폐기물 배출 신청과 수거 방법", "대형폐기물 안내")
        self.assertTrue(keywords)
        self.assertIn("폐기물", keywords)

    def test_hallucinated_department_is_removed(self):
        class Chunk:
            url = "https://www.saha.go.kr/portal/test"
            title = "폐기물 수수료"
            content = "일반침대 2인용 수수료는 18,000원입니다."
            category = "분야별정보"
            sub_category = "환경"
            chunk_index = 0
            total_chunks = 1
            department_hint = ""

        metadata = ensure_metadata({"department": "생활보장과"}, Chunk())
        self.assertIsNone(metadata["department"])

    def test_page_department_hint_overrides_llm_guess(self):
        class Chunk:
            url = "https://www.saha.go.kr/portal/test"
            title = "폐기물 수수료"
            content = "일반침대 2인용 수수료는 18,000원입니다."
            category = "분야별정보"
            sub_category = "환경"
            chunk_index = 0
            total_chunks = 1
            department_hint = "자원순환과"

        metadata = ensure_metadata({"department": "생활보장과"}, Chunk())
        self.assertEqual(metadata["department"], "자원순환과")

    def test_explicit_department_is_extracted_from_page_footer(self):
        text = "대형폐기물 처리 안내 담당자 자원순환과 (051-220-4452) 최근업데이트"
        self.assertEqual(extract_explicit_department(text), "자원순환과")


class IncrementalCrawlerTests(unittest.TestCase):
    def test_urls_seen_in_previous_menu_are_not_fetched_again(self):
        crawler = object.__new__(SahaCrawler)
        crawler.cache_validators = {}
        crawler.robot_parser = None
        crawler.fetch_page = lambda _url: self.fail("excluded URL must not be fetched")
        results = crawler.crawl_menu(
            "전자민원",
            "https://www.saha.go.kr/portal/contents.do?mId=0100000000",
            known_urls=[],
            exclude_urls={"https://www.saha.go.kr/portal/contents.do?mId=0100000000"},
        )
        self.assertEqual(results, [])

    def test_attachment_is_source_metadata_not_a_page_link(self):
        crawler = object.__new__(SahaCrawler)
        soup = BeautifulSoup(
            '<a href="/cmm/fms/FileDown.do?atchFileId=FILE_1">신청서</a>'
            '<a href="/portal/contents.do?mId=0101000000">민원 안내</a>',
            "html.parser",
        )
        links = crawler._extract_links(soup, "https://www.saha.go.kr/portal/test")
        attachments = crawler._extract_attachments(soup, "https://www.saha.go.kr/portal/test")
        self.assertEqual(links, ["https://www.saha.go.kr/portal/contents.do?mId=0101000000"])
        self.assertEqual(len(attachments), 1)
        self.assertTrue(is_non_page_url(attachments[0]["url"]))

    def test_lookalike_domain_is_rejected(self):
        crawler = object.__new__(SahaCrawler)
        soup = BeautifulSoup(
            '<a href="https://saha.go.kr.example.com/fake">위조 링크</a>',
            "html.parser",
        )
        self.assertEqual(crawler._extract_links(soup, "https://www.saha.go.kr"), [])

    def test_new_links_stay_in_their_administrative_menu(self):
        self.assertTrue(SahaCrawler._belongs_to_menu(
            "https://www.saha.go.kr/portal/contents.do?mId=0103050000", "01"
        ))
        self.assertFalse(SahaCrawler._belongs_to_menu(
            "https://www.saha.go.kr/portal/contents.do?mId=0602050000", "01"
        ))


class HybridRankingTests(unittest.TestCase):
    def test_fee_waiver_question_is_not_treated_as_staff_lookup(self):
        question = "기초생활수급자나 한부모가족은 민원 수수료를 면제받을 수 있나요?"
        self.assertFalse(HybridRetriever._has_staff_lookup_intent(question))
        self.assertFalse(HybridRetriever._has_staff_lookup_intent("주민등록번호 확인 방법"))
        self.assertTrue(HybridRetriever._has_staff_lookup_intent("대형폐기물 담당자 전화번호"))

    def test_unrelated_staff_document_is_not_used_as_source(self):
        retriever = object.__new__(HybridRetriever)
        results = [{
            "id": "staff-noise",
            "content": "감천1동 행정 업무",
            "metadata": {
                "title": "주무관",
                "url": "https://www.saha.go.kr/portal/staff/list.do?mId=0604030000",
                "category": "staff_directory",
                "department": "감천1동",
            },
            "similarity": 0.9,
        }]
        context, sources = retriever.format_context(
            "기초생활수급자 민원 수수료 면제", results
        )
        self.assertEqual(context, "")
        self.assertEqual(sources, [])

    def test_exact_bm25_match_can_beat_unrelated_vector_candidate(self):
        class FakeBm25:
            enabled = True

            @staticmethod
            def search(_query, top_n):
                return [{
                    "id": "exact",
                    "content": "대형 폐기물 배출 방법과 침대 수수료",
                    "metadata": {"title": "대형폐기물 처리 및 수수료"},
                    "bm25_score": 10.0,
                }]

        retriever = object.__new__(HybridRetriever)
        retriever.bm25 = FakeBm25()
        vector_results = [{
            "id": "semantic-noise",
            "content": "친절 공무원 추천",
            "metadata": {"title": "친절공무원 추천"},
            "similarity": 0.9,
        }]
        ranked = retriever._hybrid_combine("대형 폐기물 배출", vector_results, k=1)
        self.assertEqual(ranked[0]["id"], "exact")

    def test_strong_lexical_match_uses_fast_path_without_vector_call(self):
        class FakeBm25:
            enabled = True

            @staticmethod
            def search(_query, top_n):
                return [{
                    "id": "exact",
                    "content": "침대 대형폐기물 수수료",
                    "metadata": {
                        "title": "대형폐기물 처리 및 수수료",
                        "url": "https://www.saha.go.kr/portal/contents.do?mId=0405050103",
                    },
                    "bm25_score": 12.0,
                }]

        class NoVector:
            def hybrid_search(self, **_kwargs):
                raise AssertionError("strong lexical match must not run vector embedding")

        retriever = object.__new__(HybridRetriever)
        retriever.bm25 = FakeBm25()
        retriever.vs = NoVector()
        outcome = retriever.search("대형 폐기물 침대 수수료", k=5)
        self.assertEqual(outcome["results"][0]["id"], "exact")
        self.assertFalse(outcome["degraded"])


if __name__ == "__main__":
    unittest.main()
