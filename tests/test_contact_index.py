import unittest
from pathlib import Path

from chatbot.contact_directory import ContactDirectory
from chatbot.response_helpers import build_contextual_search_query


ROOT = Path(__file__).resolve().parent.parent


class ContactDirectoryTests(unittest.TestCase):
    def test_office_location_and_contact_is_not_staff_lookup(self):
        result = self.directory.lookup("사하구청 위치와 연락처 알려줘")
        self.assertEqual("none", result["status"])

    @classmethod
    def setUpClass(cls):
        cls.directory = ContactDirectory(ROOT / "resources" / "department_contacts.json")

    def test_dedicated_contact_file_contains_official_records(self):
        self.assertGreaterEqual(len(self.directory.data.get("departments") or []), 60)
        self.assertGreaterEqual(len(self.directory.data.get("contacts") or []), 1000)

    def test_department_phone_uses_fast_exact_lookup(self):
        result = self.directory.lookup("자원순환과 전화번호 알려줘")
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["results"][0]["department"], "자원순환과")
        self.assertRegex(result["results"][0]["phone"], r"^051-220-\d{4}$")

    def test_specific_duty_phone_uses_fast_lookup(self):
        result = self.directory.lookup("대형폐기물 담당자 전화번호 알려줘")
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["results"][0]["department"], "자원순환과")
        self.assertEqual(result["results"][0]["phone"], "051-220-4452")

    def test_ambiguous_duty_asks_for_one_condition(self):
        result = self.directory.lookup("불법주정차 담당자 전화번호 알려줘")
        self.assertEqual(result["status"], "ambiguous")
        clarification = self.directory.clarification(result)
        self.assertIn("업무명을 한 가지만", clarification["answer"])

    def test_contact_words_without_duty_do_not_guess(self):
        result = self.directory.lookup("담당자 전화번호 알려줘")
        self.assertEqual(result["status"], "ambiguous")

    def test_clarification_follow_up_resolves_previous_contact_question(self):
        history = [
            {"role": "user", "content": "불법주정차 담당자 전화번호 알려줘"},
            {"role": "assistant", "content": "민원처리인지 단속인지 알려주세요"},
        ]
        query = build_contextual_search_query("민원처리", history)
        result = self.directory.lookup(query)
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["results"][0]["phone"], "051-220-4562")


if __name__ == "__main__":
    unittest.main()
