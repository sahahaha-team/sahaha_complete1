import unittest

from chatbot.waste_schedule import WASTE_GUIDE_URL, answer_waste_schedule


class WasteScheduleTests(unittest.TestCase):
    def test_general_waste_gets_direct_verified_answer(self):
        result = answer_waste_schedule("일반쓰레기 언제 버려?")

        self.assertIsNotNone(result)
        self.assertIn("화·목·일요일", result["answer"])
        self.assertIn("19:00~22:00", result["answer"])
        self.assertIn("종량제봉투", result["answer"])
        self.assertEqual(WASTE_GUIDE_URL, result["sources"][0]["url"])
        self.assertTrue(result["verified"])
        self.assertFalse(result["degraded"])

    def test_food_waste_gets_its_own_schedule(self):
        result = answer_waste_schedule("음식물 쓰레기 배출 요일 알려줘")

        self.assertIsNotNone(result)
        self.assertIn("화·목·일요일", result["answer"])
        self.assertIn("전용 용기", result["answer"])

    def test_special_waste_is_not_intercepted(self):
        self.assertIsNone(answer_waste_schedule("대형폐기물 언제 버려?"))


if __name__ == "__main__":
    unittest.main()
