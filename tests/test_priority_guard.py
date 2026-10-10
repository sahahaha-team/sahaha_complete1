import unittest

from chatbot.priority_guard import enforce_priority_facts


class PriorityGuardTests(unittest.TestCase):
    def _result(self, approved_answer, url, required_facts=None):
        return {
            "metadata": {
                "source_priority": "priority_service",
                "approved_answer": approved_answer,
                "required_facts": required_facts or [],
                "url": url,
            }
        }

    def test_keeps_complete_llm_answer(self):
        answer = "운영시간은 09:00~18:00이며 점심시간은 12:00~13:00입니다."
        result = self._result(
            "공식 안내",
            "https://www.saha.go.kr/health/contents.do?mId=0103000000",
        )
        self.assertEqual(answer, enforce_priority_facts(answer, [result]))

    def test_replaces_incomplete_llm_answer(self):
        approved = "공식적으로 확인한 전체 요일별 배출 안내입니다."
        result = self._result(
            approved,
            "https://www.saha.go.kr/portal/contents.do?mId=0405050000",
        )
        generated = "월요일에는 재활용품을 배출합니다."
        self.assertEqual(approved, enforce_priority_facts(generated, [result]))

    def test_does_not_change_normal_answer(self):
        answer = "일반 공식 문서에 근거한 답변입니다."
        result = {"metadata": {"source_priority": "official_faq"}}
        self.assertEqual(answer, enforce_priority_facts(answer, [result]))


if __name__ == "__main__":
    unittest.main()
