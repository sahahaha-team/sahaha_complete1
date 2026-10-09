import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from chatbot.contact_directory import ContactDirectoryResponder, DIRECTORY_PATH, duty_excerpt
from scripts.build_contact_directory import parse_representatives, format_staff_phone
from crawler.staff_directory import StaffDirectoryCrawler


def fixture():
    now = datetime.now(timezone.utc).isoformat()
    def row(title, phone, duties, keywords):
        return dict(title=title, phone=phone, duties=duties, keywords=keywords)
    return {
        "schema_version": 1, "staff_checked_at": now, "representative_checked_at": now,
        "organization_phone": "051-220-4000",
        "staff_source_url": "https://www.saha.go.kr/portal/staff/list.do?mId=0604030000",
        "representative_source_url": "https://www.saha.go.kr/portal/contents.do?mId=0604060000",
        "departments": [
            {"name": "건축과", "representative_phone": "051-220-4581", "contacts": [
                row("건축과장", "051-220-4580", "건축과 업무 총괄", ["건축", "총괄"]),
                row("주무관", "051-220-4584", "위반건축물 관련 행정처리(당리,다대,장림,감천)", ["위반건축물"]),
                row("주무관", "051-220-4586", "위반건축물 관련 행정처리(괴정,하단,신평)", ["위반건축물"])]},
            {"name": "미디어홍보과", "representative_phone": "051-220-4078", "contacts": [
                row("AI행정혁신계장", "051-220-0133", "인공지능(AI) 활용 업무자동화 총괄", ["인공지능", "ai", "업무자동화"])]},
            {"name": "보건행정과", "representative_phone": "051-220-5701", "contacts": [
                row("주무관", "051-220-5763", "건강진단결과서, 건강진단서 관리", ["건강진단결과서"])]},
            {"name": "주차관리과", "representative_phone": "051-220-4514", "contacts": [
                row("주무관", "051-220-4569", "불법주정차 단속", ["불법주정차", "단속"])]},
            {"name": "환경과", "representative_phone": "051-220-4381", "contacts": [
                row("주무관", "051-220-4408", "전기차 충전시설 불법 주정차 단속", ["불법주정차", "단속", "전기차", "충전시설"])]},
            {"name": "당리동", "representative_phone": "", "contacts": []},
        ],
    }


class ContactDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "contacts.json"
        self.data = fixture()
        self.save()
        self.responder = ContactDirectoryResponder(self.path)

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def ask(self, question, session="test"):
        return self.responder.respond(session, question)

    def test_representative_is_not_head_or_fax(self):
        result = self.ask("건축과 전화번호 알려줘")
        self.assertIn("051-220-4581", result["answer"])
        self.assertNotIn("4580", result["answer"])
        self.assertIn("대표", result["answer"])
        self.assertIn("0604060000", result["sources"][0]["url"])

    def test_organization_representative_comes_from_file(self):
        self.assertIn("051-220-4000", self.ask("사하구청 대표번호 알려줘")["answer"])

    def test_department_phone_natural_wording(self):
        for query in ("건축과 전화번호 좀 알려줘", "건축과 연락처가 어떻게 돼?", "건축과 번호가 뭐야?", "건축과 대표 번호 몇번인가요?", "건축과 전화번호 알려주실 수 있나요?"):
            with self.subTest(query=query):
                self.assertIn("051-220-4581", self.ask(query)["answer"])

    def test_ai_subject_uses_real_duties(self):
        for query in ("AI 담당부서 알려줘", "인공지능 담당 부서와 연락처", "사하구청 AI 담당 전화번호"):
            with self.subTest(query=query):
                result = self.ask(query)
                self.assertIn("미디어홍보과", result["answer"])
                self.assertIn("051-220-0133", result["answer"])

    def test_natural_contact_question_grammar_is_not_an_unknown_duty(self):
        for query in (
            "사하구청에서 ai를 담당하는곳이 어디야?",
            "사하구청에서는 AI를 담당하는 부서가 어디인가요?",
            "인공지능을 담당하고 있는 팀은 어디예요?",
            "미디어홍보과에서 AI를 담당하는 곳이 어디야?",
            "보건증을 담당하는 곳이 어디야?",
        ):
            with self.subTest(query=query):
                result = self.ask(query)
                expected = "051-220-5763" if "보건증" in query else "051-220-0133"
                self.assertIn(expected, result["answer"])
                self.assertFalse(result["is_clarification"])
                self.assertTrue(result["sources"])

    def test_natural_wording_keeps_unsupported_duties(self):
        for query in (
            "사하구청에서 AI 양자컴퓨팅을 담당하는 곳이 어디야?",
            "사하구청에서 양자컴퓨팅을 담당하는 곳이 어디야?",
            "인공지능을 담당하는 곳에 양자컴퓨팅도 전화로 문의하고 싶어",
        ):
            with self.subTest(query=query):
                result = self.ask(query)
                self.assertTrue(result["is_clarification"])
                self.assertFalse(result["sources"])

    def test_alias_is_wording_only(self):
        self.assertIn("051-220-5763", self.ask("보건증 문의 전화")["answer"])
        self.assertIn("051-220-5763", self.ask("보건증을 발급받으려는데 어디에 전화해야하나요?")["answer"])

    def test_area_is_not_mistaken_for_department(self):
        result = self.ask("당리동 위반건축물 담당 전화번호")
        self.assertIn("건축과", result["answer"])
        self.assertIn("051-220-4584", result["answer"])
        self.assertNotIn("051-220-4586", result["answer"])
        self.assertIn("(당리,다대,장림,감천)", result["answer"])

    def test_multiple_departments_require_choice_with_actual_scopes(self):
        result = self.ask("불법주차 신고 전화번호")
        self.assertTrue(result["is_clarification"])
        self.assertIn("주차관리과", result["answer"])
        self.assertIn("전기차 충전시설", result["answer"])
        self.assertEqual(result["sources"], [])

    def test_unknown_and_partially_unknown_queries_do_not_guess(self):
        for query in ("양자컴퓨팅 지원 담당 부서 전화번호", "보건증 양자컴퓨팅 담당 부서 전화번호", "건축과 양자컴퓨팅 연락처"):
            result = self.ask(query)
            self.assertTrue(result["is_clarification"])
            self.assertFalse(result["sources"])

    def test_followup_and_clear(self):
        self.ask("AI 담당부서 알려줘")
        self.assertIn("051-220-0133", self.ask("그럼 그 부서 번호는?")["answer"])
        self.responder.clear("test")
        self.assertTrue(self.ask("그 업무 전화번호는?")["is_clarification"])
        self.responder.observe("other", "보건증 발급 수수료 얼마야?")
        self.assertIn("051-220-5763", self.ask("그럼 그 업무 전화번호는?", session="other")["answer"])

    def test_missing_and_stale_files_fail_closed(self):
        self.path.unlink()
        self.assertEqual(self.ask("건축과 전화번호")["degraded_reason"], "contact_directory_unavailable")
        stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        self.data["staff_checked_at"] = stale
        self.data["representative_checked_at"] = stale
        self.save()
        self.assertEqual(self.ask("AI 담당부서 알려줘")["degraded_reason"], "stale_contact_directory")
        self.assertFalse(self.ask("건축과 전화번호")["sources"])

    def test_cache_reloads_changed_file(self):
        self.ask("건축과 전화번호")
        with patch.object(Path, "read_text", side_effect=AssertionError("Repeated read")):
            self.ask("건축과 전화번호")
        self.data["departments"][0]["representative_phone"] = "051-220-9999"
        self.save()
        self.assertIn("051-220-9999", self.ask("건축과 전화번호")["answer"])

    def test_personal_info_is_blocked_before_read(self):
        with patch.object(self.responder, "_load", side_effect=AssertionError("Read")):
            result = self.ask("010-1234-5678로 연락할 보건증 담당 알려줘")
        self.assertEqual(result["evidence"]["status"], "protected")
        self.assertNotIn("010-1234", result["answer"])

    def test_non_contact_questions_keep_normal_path(self):
        for query in ("여권 수수료 얼마야", "등록된 전화번호 변경 방법", "출산지원금 신청 자격 알려줘", "담당자가 안내한 신청 조건 설명해줘"):
            self.assertIsNone(self.ask(query), query)

    def test_excerpt_preserves_parenthesized_regions(self):
        text = "기타 업무, " * 100 + "위반건축물 처리(당리,다대,장림,감천), 기타 업무"
        self.assertEqual(duty_excerpt(text, {"위반건축물"}), "위반건축물 처리(당리,다대,장림,감천)")

    def test_api_contact_route_never_initializes_chatbot(self):
        import app as web
        from fastapi.testclient import TestClient
        # No lifespan here: deliberately leave all model/database services unavailable.
        with patch.object(web, "contact_responder", self.responder), patch.object(web, "_chatbot", None), patch.object(web, "get_chatbot", side_effect=AssertionError("Heavy services accessed")):
            client = TestClient(web.app)
            result = client.post("/api/chat", json={"message": "건축과 전화번호 알려줘"})
            self.assertEqual(client.post("/api/clear").status_code, 200)
        self.assertEqual(result.status_code, 200)
        self.assertIn("051-220-4581", result.json()["answer"])

    def test_api_natural_contact_route_never_initializes_chatbot(self):
        import app as web
        from fastapi.testclient import TestClient
        with patch.object(web, "contact_responder", self.responder), patch.object(web, "_chatbot", None), patch.object(web, "get_chatbot", side_effect=AssertionError("Heavy services accessed")):
            client = TestClient(web.app)
            result = client.post("/api/chat", json={"message": "사하구청에서 ai를 담당하는곳이 어디야?"})
        self.assertEqual(result.status_code, 200)
        self.assertIn("미디어홍보과", result.json()["answer"])
        self.assertIn("051-220-0133", result.json()["answer"])
        self.assertFalse(result.json()["is_clarification"])

    def test_failed_crawl_does_not_accept_partial_pages(self):
        crawler = StaffDirectoryCrawler()
        page = '<table class="tableSt_list"><tbody><tr><td>건축과</td><td>주무관</td><td>051-220-4581</td><td>서무</td></tr></tbody></table> Page 1 / 2'
        with patch.object(crawler, "fetch_page", side_effect=[page, "empty"]):
            self.assertRaises(RuntimeError, crawler.crawl)


class OfficialSnapshotTests(unittest.TestCase):
    def test_various_departments_against_actual_snapshot(self):
        # Freshness unit tests use synthetic dates; this checks the delivered real file.
        responder = ContactDirectoryResponder(DIRECTORY_PATH)
        cases = {
            "건축과 전화번호": ("건축과", "051-220-4581"),
            "주차관리과 번호 알려줘": ("주차관리과", "051-220-4514"),
            "건강증진과 연락처": ("건강증진과", "051-220-5711"),
            "대형폐기물 담당부서 전화번호": ("자원순환과", "051-220-4452"),
            "보건증 문의 전화": ("보건행정과", "051-220-5763"),
            "출산장려금 담당부서 연락처": ("통합돌봄과", "051-220-5665"),
            "당리동 위반건축물 담당 전화번호": ("건축과", "051-220-4584"),
        }
        # Numbers are a point-in-time integration check, separate from future refreshes.
        with patch("chatbot.contact_directory.fresh", return_value=True):
            for query, (dept, phone) in cases.items():
                with self.subTest(query=query):
                    result = responder.respond(query, query)
                    self.assertIn(dept, result["answer"])
                    self.assertIn(phone, result["answer"])

    def test_phone_parser_uses_phone_column_and_both_table_halves(self):
        header = '<table><caption>사하구청 대표 전화번호와 팩스번호</caption><tbody>'
        rows = ''.join(f'<tr><td>과{i}</td><td>051-220-{4100+i}</td><td>051-220-9999</td><td>실{i}</td><td>051-220-{4200+i}</td><td>051-220-8888</td></tr>' for i in range(16))
        parsed = parse_representatives(header + rows + '</tbody></table>')
        self.assertEqual(parsed["과0"], "051-220-4100")
        self.assertEqual(parsed["실15"], "051-220-4215")
        self.assertEqual(len(parsed), 32)

    def test_official_number_formatting_preserves_digits(self):
        for raw in ("0512205974", "051)220-5974", "051-220-5974", "220-5974"):
            self.assertEqual(format_staff_phone(raw, "051"), "051-220-5974")
        self.assertEqual(format_staff_phone("not-a-number", "051"), "not-a-number")
        self.assertEqual(format_staff_phone("220-5974", "02"), "220-5974")


if __name__ == "__main__":
    unittest.main()
