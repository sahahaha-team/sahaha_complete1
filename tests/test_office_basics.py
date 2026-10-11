import unittest

from chatbot.office_basics import answer_office_basics


class OfficeBasicsTests(unittest.TestCase):
    def test_location_and_contact_returns_both_verified_facts(self):
        result = answer_office_basics("사하구청 위치와 연락처 알려줘")
        self.assertIsNotNone(result)
        self.assertIn("낙동대로398번길 12", result["answer"])
        self.assertIn("당리역 5번 출구", result["answer"])
        self.assertIn("051-220-4000", result["answer"])
        self.assertEqual(2, len(result["sources"]))
        self.assertFalse(result["degraded"])

    def test_location_only_does_not_add_phone(self):
        result = answer_office_basics("구청 주소가 어디야?")
        self.assertIsNotNone(result)
        self.assertNotIn("051-220-4000", result["answer"])
        self.assertEqual(1, len(result["sources"]))

    def test_other_location_is_not_claimed(self):
        self.assertIsNone(answer_office_basics("보건소 위치 알려줘"))


if __name__ == "__main__":
    unittest.main()
