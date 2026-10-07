import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from chatbot.response_helpers import (
    build_clarification,
    build_contextual_search_query,
    build_suggested_questions,
    is_obviously_out_of_domain,
)
from chatbot.evidence import (
    assess_evidence, select_grounded_results, is_official_document,
    filter_time_compatible, unsupported_numbers,
)
from chatbot.privacy import detect_personal_info, mask_personal_info
from processor.metadata_defaults import fallback_keywords
from processor.metadata_tagger import ensure_metadata
from chatbot.dept_directory import (
    extract_explicit_department, search_staff_directory, is_staff_lookup, staff_subject_terms,
)
from crawler.saha_crawler import SahaCrawler
from processor.data_cleaner import DataCleaner
from scripts.ingest_official_materials import _make_chunks
from chatbot.verified_facts import parse_birth_support, parse_health_certificate_fee, parse_kiosk_fee
from chatbot.source_answers import build_source_answer, source_passage, focused_section
from chatbot.faq_targets import match_official_page
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
    def test_ai_office_lookup_requires_real_ai_work_not_generic_digital_work(self):
        rows = [
            {"department": "도서관", "title": "주무관", "phone": "051-220-5861",
             "duties": "정보화교육실 및 전산장비 운영"},
            {"department": "도서관", "title": "주무관", "phone": "051-220-0162",
             "duties": "AI 우리들의 동화 운영"},
            {"department": "미디어홍보과", "title": "AI행정혁신계장", "phone": "051-220-0133",
             "duties": "인공지능(AI) 활용 업무자동화 총괄"},
        ]
        with patch("chatbot.dept_directory._row_records", return_value=rows):
            for query in ("사하구청 AI담당 부서 알려줘", "사하구청 ai 담당부서는?", "인공지능 담당 부서 연락처 알려줘"):
                self.assertTrue(is_staff_lookup(query))
                self.assertEqual(staff_subject_terms(query), {"인공지능"})
                hits = search_staff_directory(query)
                self.assertEqual(hits[0]["department"], "미디어홍보과")
                self.assertEqual(hits[0]["contact"], "051-220-0133")
                self.assertNotIn("051-220-5861", [hit["contact"] for hit in hits])
            self.assertEqual(search_staff_directory("양자컴퓨팅 담당 부서 알려줘"), [])
            self.assertEqual(search_staff_directory("담당 부서 알려줘"), [])
            self.assertEqual(search_staff_directory("airport 담당 부서 알려줘"), [])

    def test_office_lookup_is_not_reranked_into_a_notice_board(self):
        class NoVector:
            def hybrid_search(self, **_kwargs): raise AssertionError("office lookup must use verified staff")
        class NoBm25:
            def search(self, *_args, **_kwargs): raise AssertionError("board columns must not replace staff")
        retriever = object.__new__(HybridRetriever)
        retriever.vs, retriever.bm25 = NoVector(), NoBm25()
        with patch("chatbot.retriever.search_staff_directory", return_value=[{
            "score": 14, "department": "미디어홍보과", "title": "AI행정혁신계장",
            "contact": "051-220-0133", "duties": "인공지능(AI) 활용 업무자동화 총괄",
        }]):
            result = retriever.search("사하구청 AI담당 부서 알려줘")
        self.assertEqual(result["results"][0]["metadata"]["category"], "staff_directory")
        self.assertTrue(retriever.assess_evidence("사하구청 AI담당 부서 알려줘", result["results"])["confident"])

    def test_notice_board_columns_are_not_evidence_for_an_office_question(self):
        row = document(title="공지사항", content="게시판 목록\n검색어를 입력하세요.\n번호 제목 담당부서 작성일 조회", bm25=14)
        retriever = object.__new__(HybridRetriever)
        self.assertFalse(retriever.assess_evidence("사하구청 AI담당 부서 알려줘", [row])["confident"])
        self.assertEqual(retriever.select_grounded_results("사하구청 AI담당 부서 알려줘", [row]), [])
        self.assertTrue(retriever.assess_evidence("공지사항 게시판 알려줘", [row])["confident"])

    def test_full_source_board_header_blocks_a_later_retrieval_chunk(self):
        class Query:
            def select(self, *_args): return self
            def eq(self, *_args): return self
            def limit(self, *_args): return self
            def execute(self): return type("Response", (), {"data": [{
                "content": "공지사항\n게시판 목록\n검색영역선택항목\n번호 제목 담당부서 작성일 조회\n행사 안내"
            }]})()
        class Client:
            def table(self, *_args): return Query()
        row = document(content="담당부서 환경과 2026.04.14", bm25=14)
        self.assertEqual(build_source_answer([row], Client(), query="AI 담당 부서 알려줘"), ("", []))

    def test_staff_answer_names_the_verified_office_and_contact_without_raw_page(self):
        class NoClient:
            def table(self, *_args): raise AssertionError("verified staff must not fetch a notice page")
        row = document(title="AI행정혁신계장", content="공식 담당부서: 미디어홍보과\n업무: 인공지능(AI) 활용 업무자동화 총괄")
        row["metadata"].update(category="staff_directory", department="미디어홍보과", contact="051-220-0133")
        answer, used = build_source_answer([row], NoClient(), query="사하구청 AI담당 부서 알려줘")
        self.assertIn("**미디어홍보과**", answer)
        self.assertIn("**051-220-0133**", answer)
        self.assertNotIn("게시판 목록", answer)
        self.assertEqual(used, [row])

    def test_new_adult_passport_cannot_quote_emergency_or_official_passport_requirements(self):
        url = "https://www.saha.go.kr/portal/contents.do?mId=0104020000"
        text = ("신규발급\n일반여권\n여권발급신청서 1부\n신분증\n사진 2매\n"
                "만18세 미만 미성년자의 여권 신청\n법정대리인\n긴급여권\n항공권 사본\n"
                "관용여권\n공무원증 또는 재직증명서 1부")
        query = "성인이 여권을 새로 만들 때 무엇을 준비해야 하나요?"
        section = focused_section(query, url, text)
        self.assertIn("사진 2매", section)
        self.assertNotIn("공무원증", section)
        self.assertNotIn("항공권", section)
        self.assertEqual(focused_section(query, url, "바뀐 페이지"), "")

    def test_kiosk_free_rule_keeps_the_paid_exception(self):
        content = ("수수료 지불 방법 : 무료 (2026.1.1.부터)\n"
                   "단, 부동산등기부등본 1000원(현금만 가능) / 법인용 무인민원발급기는 현금 & 카드\n"
                   "설치장소 및 운영시간\n부동산등기부등본 및 가족관계증명 발급가능")
        answer = parse_kiosk_fee(content)
        self.assertIn("1000원", answer)
        self.assertIn("다만", answer)
        self.assertIsNone(parse_kiosk_fee("부동산등기부등본 및 가족관계증명 발급가능"))

    def test_source_answer_preserves_conditions_without_model_synthesis(self):
        original = "무료법률상담 안내\n방 법\n: 전화예약 후 방문상담\n상담일정 : 매월 2, 4주 수요일 오후 2시～5시"
        class Query:
            def select(self, *_args): return self
            def eq(self, *_args): return self
            def limit(self, *_args): return self
            def execute(self): return type("Response", (), {"data": [{"content": original}]})()
        class Client:
            def table(self, *_args): return Query()
        row = document(title="무료법률상담안내", content=original)
        answer, used = build_source_answer([row], Client())
        self.assertIn("> : 전화예약 후 방문상담", answer)
        self.assertNotIn("전화 상담으로 가능합니다", answer)
        self.assertEqual(used, [row])
        self.assertEqual(source_passage("인쇄하기\n" + original + "\n만족도조사\n5점", ""), original)

    def test_missing_original_cannot_fall_back_to_unverified_model_answer(self):
        class Client:
            def table(self, *_args): raise RuntimeError("offline")
        self.assertEqual(build_source_answer([document(content="낡은 검색 청크")], Client()), ("", []))

    def test_year_must_come_from_body_or_report_data_period(self):
        page = document(content="2025년 접수 건수 100건")
        self.assertEqual(filter_time_compatible("2026년 접수 건수", [page]), [])
        report = document(title="2026년 정보공개청구 분석 보고서", content="2025년 100건",
                          url="file://official_reports/abc/page-3")
        report["metadata"].update(source_type="official_report", issued_at="2026-08-04",
                                 data_period="2023-01-01~2025-12-31")
        self.assertEqual(filter_time_compatible("2027년 정보공개청구 건수", [report]), [])
        self.assertEqual(filter_time_compatible("2024년 정보공개청구 건수", [report]), [report])

    def test_official_question_maps_to_url_without_using_draft_answer(self):
        with patch("chatbot.faq_targets._targets", return_value=[
            ("사하구청은어디에있나요", "https://www.saha.go.kr/portal/location")
        ]):
            self.assertEqual(match_official_page("사하구청은 어디에 있나요?"),
                             "https://www.saha.go.kr/portal/location")
            self.assertIsNone(match_official_page("사하구청 부동산 가격을 예측해줘"))

    def test_exact_rows_prevent_mixing_birth_and_health_fees(self):
        birth = (
            "첫만남이용권 첫째 200만원 "
            "출산지원금(구비, 시비) 사하구에 주민등록 되어있는 26년 모든 출생아 "
            "첫째부터 50만원 (현금, 일시금) 부산시에 주민등록 되어있는 26년 둘째이후 출생아 "
            "둘째이후 100만원 (현금, 일시금) 출산지원금(장애인) 별도"
        )
        answer = parse_birth_support(birth)
        self.assertIn("50만원", answer)
        self.assertIn("100만원", answer)
        self.assertNotIn("200만원", answer)
        fees = "2026년 제증명 수수료 내역 건강진단결과서 (구 보건증) 3,000원 5일 일반건강진단서"
        self.assertIn("3,000원", parse_health_certificate_fee(fees))
        self.assertIn("5일", parse_health_certificate_fee(fees))

    def test_birth_benefit_programs_are_split_before_embedding(self):
        page = type("Page", (), {})()
        page.url = "https://www.saha.go.kr/portal/contents.do?mId=0510070100"
        page.title = "출산장려정책"
        page.category = "사하복지"
        page.sub_category = "지원"
        page.content = (
            "첫만남이용권\n첫째 200만원, 둘째 300만원\n"
            "출산지원금(구비, 시비)\n2026년 모든 출생아 첫째부터 50만원\n"
            "출산지원금(장애인)\n별도 지원"
        )
        chunks = _make_chunks(DataCleaner(), page)
        cash = [c.content for c in chunks if "출산지원금(구비, 시비)" in c.content]
        self.assertTrue(cash)
        self.assertTrue(all("200만원" not in item for item in cash))

    def test_lookalike_domain_is_not_official(self):
        self.assertFalse(is_official_document(document(url="https://saha.go.kr.example.com/fake")))
        self.assertFalse(is_official_document(document(url="file://unverified/report.pdf")))

    def test_historical_report_cannot_answer_current_or_2026_counts(self):
        report = document(title="2026년 정보공개청구 분석 보고서", content="2025년 처리 1,963건",
                          url="file://official_reports/abc/page-3")
        report["metadata"].update(source_type="official_report", data_period="2023-01-01~2025-12-31")
        self.assertEqual(filter_time_compatible("현재 정보공개청구는 몇 건?", [report]), [])
        self.assertEqual(filter_time_compatible("2026년 정보공개청구 건수", [report]), [])
        self.assertEqual(filter_time_compatible("2026년 정보공개청구 분석 보고서는?", [report]), [report])

    def test_numerical_claim_must_exist_in_retrieved_context(self):
        context = "건강진단결과서 3,000원, 5일. 2026.1.1.부터"
        self.assertEqual(unsupported_numbers("수수료는 3,000원입니다.", context), [])
        self.assertEqual(unsupported_numbers("2026년부터 무료입니다.", context), [])
        self.assertEqual(unsupported_numbers("수수료는 7,000원입니다.", context), ["7000"])

    def test_stale_web_page_is_not_used_for_current_fee(self):
        class Response:
            data = [{"url": "https://www.saha.go.kr/fee", "last_checked_at":
                     (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()}]

        class Table:
            def select(self, *_args): return self
            def in_(self, *_args): return self
            def execute(self): return Response()

        class Client:
            def table(self, *_args): return Table()

        retriever = object.__new__(HybridRetriever)
        retriever.db = type("DB", (), {"client": Client()})()
        row = document(title="발급 수수료", url="https://www.saha.go.kr/fee")
        self.assertEqual(retriever.filter_fresh_results("현재 발급 수수료는?", [row]), [])

    def test_report_context_includes_period_without_local_file_link(self):
        retriever = object.__new__(HybridRetriever)
        row = document(title="정보공개청구 분석 (3쪽)", content="2024년 청구 2,216건",
                       url="file://official_reports/abc/page-3")
        row["metadata"].update(source_type="official_report", issued_at="2026-08-04",
                               data_period="2023-01-01~2025-12-31", page_number="3")
        context, sources = retriever.format_context("2024년 정보공개청구 건수", [row])
        self.assertIn("2023-01-01~2025-12-31", context)
        self.assertEqual(sources[0]["url"], "")
        self.assertEqual(sources[0]["page_number"], 3)

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

    def test_admin_intent_alone_cannot_establish_answer_evidence(self):
        results = [document(title="온라인 처리 안내", content="필요한 절차와 준비사항", similarity=0.62)]
        evidence = assess_evidence(results, keywords={"민원", "신청"}, domain_intent=True, min_similarity=0.45)
        self.assertFalse(evidence["confident"])
        self.assertEqual(evidence["status"], "insufficient")

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

    def test_vague_request_produces_clarification_and_choices(self):
        result = build_clarification("지원받고 싶어요")
        self.assertIsNotNone(result)
        self.assertEqual(len(result["suggested_questions"]), 3)

    def test_specific_request_does_not_trigger_clarification(self):
        self.assertIsNone(build_clarification("장애인 활동지원 신청 방법 알려줘"))

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

    def test_new_topic_does_not_inherit_previous_question(self):
        history = [{"role": "user", "content": "정보공개청구 통계를 알려줘"}]
        query = build_contextual_search_query("2026년 출산지원금은 얼마인가요?", history)
        self.assertEqual(query, "2026년 출산지원금은 얼마인가요?")


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
    def test_robots_denied_known_page_is_not_reported_as_deleted(self):
        crawler = object.__new__(SahaCrawler)
        crawler.cache_validators = {}
        crawler.robot_parser = None
        crawler._can_fetch = lambda _url: False
        url = "https://www.saha.go.kr/portal/contents.do?mId=0103040000"
        results = crawler.crawl_menu("전자민원", url, known_urls=[url])
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].transient_fail)

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
