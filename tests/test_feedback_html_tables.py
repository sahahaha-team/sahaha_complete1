"""Search chunks must retain the same table ownership as official answers."""
import unittest
from bs4 import BeautifulSoup
from crawler.saha_crawler import SahaCrawler
from chatbot.official_content import table_units
from processor.data_cleaner import DataCleaner


class FeedbackHtmlTableTests(unittest.TestCase):
    def search(self, html):
        return object.__new__(SahaCrawler)._extract_content(BeautifulSoup(html, 'lxml'))

    def test_merged_day_and_time_stay_with_each_material_in_search_chunks(self):
        html = '''<main><h3>분리배출</h3><table>
        <tr><th>요일</th><th>품목</th><th>시간</th></tr>
        <tr><th rowspan="2">월요일</th><td>플라스틱</td><td rowspan="2">19~22시</td></tr>
        <tr><td>비닐</td></tr>
        <tr><th>수요일</th><td>종이</td><td>19~22시</td></tr></table></main>'''
        expected = table_units(BeautifulSoup(html, 'lxml').table)
        search = self.search(html)
        for unit in expected:
            self.assertIn(unit, search)
        self.assertIn('월요일 — 품목: 비닐', search)
        self.assertNotIn('수요일 — 품목: 비닐', search)
        chunks = DataCleaner().split_structured_text(search)
        self.assertTrue(any('분리배출' in c and '월요일 — 품목: 비닐' in c for c in chunks))

    def test_civil_table_keeps_title_and_document_labels(self):
        html = '''<main><table class="tableSt_view">
        <tr><th colspan="2" class="title">주민등록 신고</th></tr>
        <tr><th>구비서류</th><td><p>신분증</p><p>대리 신청 시 위임장</p></td></tr>
        <tr><th>처리기간</th><td>접수 후 3일</td></tr></table></main>'''
        search = self.search(html)
        self.assertIn('### 주민등록 신고', search)
        self.assertIn('구비서류: 대리 신청 시 위임장', search)
        self.assertIn('처리기간: 접수 후 3일', search)

    def test_ambiguous_merged_layout_never_flattens_into_unowned_facts(self):
        html = '''<main><h3>신청 안내</h3><p>현재 안내 내용을 확인하세요.</p>
        <table><tr><th colspan="invalid">대상</th><td>다른 사업의 조건</td></tr></table></main>'''
        self.assertNotIn('다른 사업의 조건', self.search(html))


if __name__ == '__main__':
    unittest.main()
