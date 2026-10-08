import time
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from chatbot.query_subject import query_keywords, fallback_keywords
from chatbot.evidence import topic_support, select_grounded_results, is_service_source
from chatbot.crawled_pages import CrawledPageIndex
from chatbot.concise_answers import concise_source_answer, scope_question
from chatbot.source_answers import build_source_answer
from chatbot.retriever import HybridRetriever
from chatbot.response_helpers import build_clarification


def doc(title, content, url="https://www.saha.go.kr/portal/contents.do?mId=0102010000"):
    return {"content": content, "metadata": {"title": title, "url": url, "source_type": "crawled_page"}}


def quoted(body):
    return "공식 원문\n" + "\n".join("> " + line for line in body.splitlines())


class GeneralTopicTests(unittest.TestCase):
    def test_passport_spelling_request_does_not_return_a_generic_menu(self):
        self.assertIsNone(build_clarification("여권 영문성명은 어떻게 표기하나요?"))

    def test_named_center_is_not_mistaken_for_generic_welfare_support(self):
        self.assertIsNone(build_clarification("사하구 건강생활지원센터에서는 어떤 서비스를 이용할 수 있나요?"))
        self.assertIsNone(build_clarification("암환자 의료비 지원을 받을 수 있나요?"))
        self.assertIsNotNone(build_clarification("사하구 복지 지원 알려줘"))

    def test_service_names_survive_morphology(self):
        self.assertEqual(query_keywords("전입신고 어떻게 해?", ["전입", "신고"]), {"전입신고"})
        self.assertEqual(query_keywords("주민등록등본 발급 방법", ["주민", "등록", "등본", "방법"]), {"주민등록등본"})

    def test_free_and_no_charge_are_equivalent_for_search_only(self):
        row = doc("폐가전", "냉장고 무상수거 신청방법 : 전화 예약")
        self.assertTrue(topic_support(row, {"냉장고", "무료", "수거"})[0])

    def test_facility_is_kept_but_request_words_are_not_topics(self):
        self.assertEqual(fallback_keywords("사하구청 위치 알려줘"), {"구청"})
        self.assertEqual(query_keywords("재산세 어떤 날짜 기준으로 누가 내나요?", ["재산세", "날짜", "기준"]), {"재산세"})

    def test_missing_service_cannot_be_outvoted_by_conditions(self):
        row = doc("폭염", "거동이 불편한 사람의 건강 관리")
        self.assertFalse(topic_support(row, {"거동", "불편", "관리", "방문건강"})[0])

    def test_health_scope_needs_actual_service_body(self):
        row = doc("물리치료실", "물리치료 대상 : 의사 처방이 필요한 분", "https://www.saha.go.kr/health/contents.do?mId=0201020000")
        self.assertTrue(topic_support(row, {"보건소", "물리치료"})[0])
        row["content"] = "주차 안내"
        row["metadata"]["title"] = "찾아오시는 길"
        self.assertFalse(topic_support(row, {"보건소", "물리치료"})[0])

    def test_collective_certificate_name_supports_both(self):
        row = doc("정부24", "주민등록 등·초본을 인터넷으로 발급")
        self.assertTrue(topic_support(row, {"주민등록등본"})[0])
        self.assertTrue(topic_support(row, {"주민등록초본"})[0])

    def test_benefit_required_certificate_is_not_issuance(self):
        row = doc("산모신생아 건강관리지원", "구비서류 : 주민등록등본\n국민행복카드를 발급합니다.")
        self.assertFalse(is_service_source("주민등록등본 발급 방법", row, {"주민등록등본"}))

    def test_independent_urls_are_not_crowded_out_by_chunks(self):
        first = doc("정화조", "정화조 청소")
        next_doc = doc("정화조", "정화조 청소 주기", first["metadata"]["url"] + "2")
        result = select_grounded_results([first]*8+[next_doc], keywords={"정화조"}, domain_intent=True, min_similarity=.45, limit=2)
        self.assertEqual(result, [first, next_doc])


class CrawledSourceTests(unittest.TestCase):
    def index(self, pages):
        index = CrawledPageIndex(Mock())
        index._pages = pages
        index._loaded_at = time.monotonic()
        return index

    def page(self, title, content, *, days=0, url="https://www.saha.go.kr/portal/contents.do?mId=123"):
        return {"url": url, "title": title, "content": "Home\n인쇄하기\n" + content + "\n만족도조사\n평점", "category": "분야별정보",
            "last_checked_at": (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()}

    def test_crawler_original_without_any_embedding_is_searchable(self):
        r = object.__new__(HybridRetriever)
        r.bm25 = SimpleNamespace(enabled=False)
        r.page_index = self.index([self.page("정화조 청소", "정화조는 연 1회 청소해야 합니다.")])
        r.vs = Mock()
        result = r.search("정화조 청소 주기")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["metadata"]["source_type"], "crawled_page")
        r.vs.hybrid_search.assert_not_called()

    def test_stale_external_and_landing_pages_are_excluded(self):
        pages = [self.page("정화조", "정화조 청소 방법", days=45),
            self.page("정화조", "정화조 청소 방법", url="https://saha.go.kr.example.com/fake"),
            self.page("정화조", "정화조 청소 방법", url="https://www.saha.go.kr/sinpyeong1/main.do")]
        self.assertEqual(self.index(pages).search("정화조 청소 방법", {"정화조", "청소"}), [])

    def test_misleading_title_cannot_support_an_unrelated_body(self):
        index = self.index([self.page("전입신고", "주차 단속 신고 방법")])
        self.assertEqual(index.search("전입신고 방법", {"전입신고"}), [])

    def test_intent_selection_tries_next_distinct_source(self):
        originals = {"first": "정화조 청소란 시설을 유지하는 작업입니다.",
            "second": "정화조 청소 신청방법 : 처리업체에 전화로 예약하세요."}
        class Query:
            def select(self, *_): return self
            def eq(self, _field, url): self.url = url; return self
            def limit(self, *_): return self
            def execute(self): return SimpleNamespace(data=[{"content": originals[self.url.rsplit('/',1)[-1]]}])
        client = SimpleNamespace(table=lambda _: Query())
        first = doc("정화조 청소", originals["first"], "https://www.saha.go.kr/first")
        second = doc("정화조 청소", originals["second"], "https://www.saha.go.kr/second")
        answer, used = build_source_answer([first]*8+[second], client, query="정화조 청소 신청 방법", topic_keywords={"정화조", "청소"}, require_brief=True)
        self.assertEqual(used, [second])
        self.assertIn("전화로 예약", answer)


class GeneralBriefTests(unittest.TestCase):
    def test_free_exclusion_after_product_table_is_retained(self):
        body = "폐가전\n신청방법 : 콜센터(1599-0903), 인터넷(http://example.test)\n단일수거\n냉장고, 에어컨\n가능 제품 안내\n※ 원형훼손 제품(냉장고 냉각기 훼손)은 무상 수거가 되지 않음.\n※ 안마의자는 제외"
        result = concise_source_answer("냉장고 무료 수거 신청 방법", quoted(body), [doc("폐가전", body)], {"냉장고", "무상", "수거"})
        self.assertFalse(result["is_clarification"])
        self.assertIn("원형훼손", result["answer"])
        self.assertNotIn("안마의자", result["answer"])

    def test_services_question_uses_actual_contents_not_purpose(self):
        body = "건강생활지원센터 운영\n사업목적\n지역사회 건강수준 향상에 기여\n운영내용\n건강측정(혈압, 혈당) 및 상담\n고혈압, 당뇨 등 만성질환관리\n위치 및 운영시간\n09:00 ~ 18:00"
        result = concise_source_answer("건강생활지원센터 어떤 서비스를 이용할 수 있나요?", quoted(body), [doc("건강생활지원센터", body)], {"건강생활지원센터"})
        self.assertFalse(result["is_clarification"])
        self.assertIn("혈압", result["answer"])
        self.assertIn("만성질환관리", result["answer"])
        self.assertNotIn("09:00", result["answer"])

    def test_certificate_method_does_not_select_a_required_card(self):
        body = "산모신생아 건강관리지원\n주민등록등본을 제출하세요.\n국민행복카드를 발급하세요."
        row = doc("산모신생아 건강관리지원", body)
        self.assertFalse(is_service_source("주민등록등본 발급 방법", row, {"주민등록등본"}))

    def test_free_collection_retains_damage_exception(self):
        body = "폐기물\n아래 물품중 냉장고, 세탁기는 무상수거 (콜센터 1599-0903) 단, 원형훼손제품은 제외 (유상 처리)"
        result = concise_source_answer("냉장고 무료 수거 신청 방법", quoted(body), [doc("폐기물", body)], {"냉장고", "무상", "수거"})
        self.assertFalse(result["is_clarification"])
        self.assertIn("1599-0903", result["answer"])
        self.assertIn("유상 처리", result["answer"])

    def test_electronic_application_keeps_channel_and_login(self):
        body = "전자민원창구\n민원신청 안내\n민원상담은 국민신문고로 통합하여 운영하고 있습니다.\n별도 회원가입 또는 로그인이 필요합니다."
        result = concise_source_answer("사하구청에 온라인으로 민원을 신청하려면 어떻게 하나요?", quoted(body), [doc("전자민원창구", body)], {"전자민원"})
        self.assertIn("국민신문고", result["answer"])
        self.assertIn("로그인", result["answer"])

    def test_wrapped_internet_method_is_complete(self):
        body = "정부24\n정부24는 어디서나 필요한 민원을\n인터넷을 이용\n해 신청·열람·발급받을 수 있는 정부서비스입니다."
        result = concise_source_answer("정부24 이용 방법", quoted(body), [doc("정부24", body)], {"정부24"})
        self.assertFalse(result["is_clarification"])
        self.assertIn("인터넷을 이용 해 신청", result["answer"])
        self.assertTrue(result["answer"].endswith("입니다."))

    def test_short_frequency_question_uses_frequency_not_another_field(self):
        body = "정화조 청소\n정화조는 연 1회 이상 내부청소를 해야 합니다.\n신청방법 : 업체에 전화하세요."
        result = concise_source_answer("정화조는 얼마나 자주 청소해야 하나요?", quoted(body), [doc("정화조 청소", body)], {"정화조", "청소"})
        self.assertIn("연 1회", result["answer"])
        self.assertNotIn("전화", result["answer"])

    def test_clear_method_request_does_not_ask_to_choose_method_again(self):
        result = scope_question("전입신고 방법 알려줘", "신청방법 및 준비서류")
        self.assertNotIn("신청 방법·", result["answer"])

    def test_flat_money_cells_are_not_reassigned_to_a_subject(self):
        body = "여권 수수료\n58면\n52,000원\n26면\n49,000원"
        result = concise_source_answer("여권 수수료 얼마야", quoted(body), [doc("여권", body)], {"여권"})
        self.assertTrue(result["is_clarification"])

    def test_source_details_and_exception_remain_intact(self):
        body = "정화조 청소\n정화조 청소 신청방법 : 전화로 예약하세요.\n다만 대상에 해당하지 않으면 신청할 수 없습니다."
        result = concise_source_answer("정화조 청소 신청방법", quoted(body), [doc("정화조 청소", body)], {"정화조", "청소"})
        self.assertIn("다만", result["answer"])
        self.assertEqual(result["answer_details"], quoted(body))


if __name__ == "__main__":
    unittest.main()
