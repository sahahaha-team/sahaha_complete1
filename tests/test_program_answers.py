import unittest

from chatbot.faq_targets import find_program_service, match_official_page
from chatbot.program_answers import (
    answer_program_alternatives,
    program_overview_answer,
    wants_program_overview,
)


FIRE_URL = "https://www.saha.go.kr/reserve/contents.do?mId=1207000000"
LIBRARY_URL = "https://www.saha.go.kr/portal/contents.do?mId=0408030000"


class ProgramRoutingTests(unittest.TestCase):
    def test_fire_program_is_found_from_natural_discovery_question(self):
        query = "소방 관련 프로그램이 있는 걸로 아는데 설명해줘"
        self.assertEqual(FIRE_URL, match_official_page(query))
        self.assertEqual(1002, find_program_service(query)["id"])

    def test_other_named_program_uses_its_own_page(self):
        self.assertEqual(
            LIBRARY_URL,
            match_official_page("작은도서관 관련 교육 프로그램을 설명해줘"),
        )

    def test_library_discovery_wording_does_not_change_the_route(self):
        variants = (
            "도서관 관련 프로그램이 있다고 하는데",
            "도서관에서 하는 프로그램이 뭐가 있어?",
            "도서관 프로그램이 있다던데 소개해줘",
            "도서관 관련 프로그램이 있는 걸로 아는데",
        )
        for query in variants:
            with self.subTest(query=query):
                self.assertEqual(LIBRARY_URL, match_official_page(query))
                self.assertTrue(wants_program_overview(query))

    def test_generic_program_question_is_not_assigned_arbitrarily(self):
        self.assertIsNone(find_program_service("프로그램에는 무엇이 있어?"))


class ProgramOverviewTests(unittest.TestCase):
    BODY = """이용안내
예약안내 및 예약
소방특화 들락날락
전화번호 : 051-271-6835
운영시간 : 화요일~토요일, 09:00~18:00
이용료 : 무료
이용대상 :
4세 이상 13세 이하 어린이
체험관을 이용하고자 하는 경우 3개월 전 매월 1일 9시부터 예약 신청 가능합니다.
1F 실감형 가상재난 체험관, 소방안전 어린이 작은도서관
2F 소방안전교육센터(심폐소생술 체험관)
3F 소방차 출동 시뮬레이터, 화재진압 체험관
4F 비상대피 체험관, 화재 건물대피 체험관"""

    def test_overview_uses_program_content_not_menu_heading(self):
        document = {"metadata": {"title": "이용안내", "url": FIRE_URL}}
        result = program_overview_answer(
            "소방특화 들락날락 프로그램을 설명해줘", document, self.BODY
        )

        self.assertIsNotNone(result)
        self.assertIn("소방특화 들락날락", result["answer"])
        self.assertIn("4세 이상 13세 이하", result["answer"])
        self.assertIn("무료", result["answer"])
        self.assertIn("가상재난 체험관", result["answer"])
        self.assertNotIn("짧은 바지", result["answer"])
        self.assertNotEqual("이용안내\n- 예약안내 및 예약", result["answer"])
        self.assertEqual(
            "소방특화 들락날락 체험 이용안내",
            result["documents"][0]["metadata"]["title"],
        )

    def test_other_program_followup_excludes_the_program_just_explained(self):
        result = answer_program_alternatives(
            "소방특화 들락날락 프로그램 설명해줘 다른 프로그램 뭐 있어?"
        )

        self.assertIsNotNone(result)
        self.assertNotIn("소방특화 들락날락 체험**", result["answer"])
        self.assertIn("작은도서관 교육 프로그램", result["answer"])
        self.assertIn("평생학습관 프로그램", result["answer"])
        self.assertEqual(4, result["evidence"]["official_source_count"])
        self.assertEqual("program_alternatives", result["evidence"]["answer_method"])
        self.assertIsNone(answer_program_alternatives(
            "다른 프로그램 뭐 있어? 작은도서관은?", current_query="작은도서관은?"
        ))

    def test_detail_followup_includes_program_schedule_and_contact(self):
        body = """작은도서관 프로그램 운영 안내
대 상 : 사하구민
수 강 료 : 무료(단, 교재 및 재료비 별도)
운영기간 : 연중
겨울방학
1월
체험형 동화구연
3월~12월
도서관주간 행사
4월
원데이 특강
5월~6월
11월~12월
어린이 독서캠프
10월
접수방법 : 온라인접수(사하구 통합예약)
문 의 : 사하구 평생교육과(☎ 051-220-4834)"""
        result = program_overview_answer(
            "작은도서관 프로그램 자세히 설명해줄래?",
            {"metadata": {"title": "작은도서관", "url": LIBRARY_URL}},
            body,
        )

        self.assertIn("대상 : 사하구민", result["answer"])
        self.assertIn("운영기간 : 연중", result["answer"])
        self.assertIn("체험형 동화구연: 3월~12월", result["answer"])
        self.assertIn("원데이 특강: 5월~6월, 11월~12월", result["answer"])
        self.assertNotIn("5월~6월: 11월~12월", result["answer"])
        self.assertIn("051-220-4834", result["answer"])


if __name__ == "__main__":
    unittest.main()
