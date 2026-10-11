import threading
import unittest
from unittest.mock import Mock

from chatbot.conversation import ChatBot
from chatbot.response_helpers import build_contextual_search_query
from chatbot.waste_schedule import answer_waste_schedule


class ContextualFollowupTests(unittest.TestCase):
    def test_bare_alternative_inherits_previous_question_intent(self):
        history = [
            {"role": "user", "content": "일반쓰레기 언제 버려?", "search_query": "일반쓰레기 언제 버려?"},
            {"role": "assistant", "content": "화·목·일요일에 배출하세요."},
        ]

        resolved = build_contextual_search_query("음식물쓰레기는?", history)

        self.assertIn("일반쓰레기 언제 버려?", resolved)
        self.assertTrue(resolved.endswith("음식물쓰레기는?"))
        result = answer_waste_schedule(resolved)
        self.assertIsNotNone(result)
        self.assertIn("음식물쓰레기는", result["answer"])
        self.assertIn("화·목·일요일", result["answer"])

    def test_context_is_scoped_to_the_same_session(self):
        bot = object.__new__(ChatBot)
        bot.db = None
        bot._memory_history = {}
        bot._history_lock = threading.RLock()
        bot._pending_clarifications = {}
        bot._save_conversation_safe("first", "user", "일반쓰레기 언제 버려?", search_query="일반쓰레기 언제 버려?")
        bot._save_conversation_safe("first", "assistant", "화·목·일요일에 배출하세요.")

        self.assertIn("일반쓰레기 언제 버려?", bot.contextual_message("first", "음식물쓰레기는?"))
        self.assertEqual("음식물쓰레기는?", bot.contextual_message("other", "음식물쓰레기는?"))

    def test_persistent_history_is_used_for_context_too(self):
        bot = object.__new__(ChatBot)
        bot.db = Mock()
        bot.db.get_conversation_history.return_value = [
            {"role": "user", "content": "일반쓰레기 언제 버려?"},
            {"role": "assistant", "content": "화·목·일요일에 배출하세요."},
        ]
        bot._memory_history = {}
        bot._history_lock = threading.RLock()
        bot._pending_clarifications = {}

        resolved = bot.contextual_message("persisted", "음식물쓰레기는?")

        self.assertIn("일반쓰레기 언제 버려?", resolved)
        self.assertTrue(resolved.endswith("음식물쓰레기는?"))
        bot.db.get_conversation_history.assert_called_once()

    def test_complete_location_question_does_not_inherit_old_topic(self):
        history = [{"role": "user", "content": "일반쓰레기 언제 버려?"}]

        self.assertEqual(
            "보건소 위치는?",
            build_contextual_search_query("보건소 위치는?", history),
        )

    def test_other_and_intent_only_questions_inherit_previous_topic(self):
        history = [
            {"role": "user", "content": "소방특화 들락날락 프로그램 설명해줘"},
            {"role": "assistant", "content": "소방안전 체험 프로그램입니다."},
        ]

        other = build_contextual_search_query("다른 프로그램 뭐 있어?", history)
        method = build_contextual_search_query("신청은 어떻게 해?", history)

        self.assertIn("소방특화 들락날락", other)
        self.assertTrue(other.endswith("다른 프로그램 뭐 있어?"))
        self.assertIn("소방특화 들락날락", method)
        self.assertTrue(method.endswith("신청은 어떻게 해?"))

        detail = build_contextual_search_query("자세히 설명해줄래?", history)
        self.assertIn("소방특화 들락날락", detail)
        self.assertTrue(detail.endswith("자세히 설명해줄래?"))


if __name__ == "__main__":
    unittest.main()
