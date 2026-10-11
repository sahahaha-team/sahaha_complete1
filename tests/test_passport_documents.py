"""Passport documents must keep applicant age, visitor and source ownership."""
import unittest
import re
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from chatbot.official_content import official_html_text
from chatbot.passport_documents import (parse_passport_documents, applicant_age,
    answer_passport_documents, PASSPORT_URL)
from chatbot.response_helpers import build_clarification, resolve_clarification_reply


# Same nested-list shape and wording as the live official Saha guide: each
# visitor's requirements become one outer paragraph in the shared HTML parser.
HTML = '''<div id="contents"><h2>여권발급안내</h2><div id="conts">
<h3>여권발급 주요 내용</h3>
<li>미성년자의 사진 및 구여권(유효기간 만료 전 여권), 법정대리인 신분증 지참</li>
<h3>신규발급</h3><h5>일반여권</h5>
<ul><li>여권발급신청서 1부 ※ 구청 민원실 비치</li><li>신분증(주민등록증, 운전면허증 등)</li>
<li>여권용 컬러 사진 2매(최근 6개월 이내 촬영, 가로 3.5cm×세로 4.5cm, 정수리~턱까지의 길이가 3.2~3.6㎝)</li>
<li>만18세 미만 미성년자의 여권 신청<ul>
<li>친권자(혹은 법정대리인) 신청시 : 친권자(혹은 법정대리인) 신분증, 법정대리인 동의서</li>
<li>미성년자 본인 신청서 : 친권자(혹은 법정대리인)의 신분증, 인감증명서 및 인감도장, 법정대리인 동의서, 미성년자 본인 신분증(학생증 혹은 청소년증 등)</li>
<li>미성년자의 2촌 이내 친족(만18세 이상) 신청 시 : 법정대리인 동의서, 친권자의 인감증명서 및 인감도장, 위임장 및 위임자(법정대리인) 신분증(사본가능), 방문한 대리인의 신분증</li>
</ul></li></ul>
<h4>긴급여권</h4><li>항공권 사본</li><h4>관용여권</h4><li>공무원증 또는 재직증명서 1부</li>
<h4>재발급</h4><li>구비서류<ul><li>여권발급신청서 1부</li><li>신분증(주민등록증, 운전면허증 등)</li>
<li>여권용 컬러 사진 2매(최근 6개월 이내 촬영, 가로 3.5cm×세로 4.5cm, 정수리~턱까지의 길이가 3.2~3.6㎝)</li>
<li>유효기간 남은 여권은 지참</li></ul></li>
<h3>여권발급 등에 관한 수수료</h3><li>52,000원</li>
<h3>국제운전면허증 신청</h3><li>사진1매</li></div></div>'''


class Client:
    def __init__(self, row): self.row, self.url = row, None
    def table(self, name): assert name == 'raw_pages'; return self
    def select(self, fields): return self
    def eq(self, field, value): self.url = value; return self
    def limit(self, value): return self
    def execute(self): return SimpleNamespace(data=[self.row])


class PassportDocumentsTests(unittest.TestCase):
    def setUp(self): self.body = official_html_text(HTML)

    def test_renewal_reads_current_documents_and_existing_passport(self):
        answer = parse_passport_documents('성인 여권 재발급 준비물 알려줘', self.body)
        for fact in ('신청서 1부', '사진 2매', '6개월', '3.5cm', '4.5cm', '기존 여권'):
            self.assertIn(fact, answer)
        self.assertNotIn('공무원증', answer)
        self.assertNotIn('항공권', answer)
        self.assertLessEqual(len(answer), 480)

    def test_parent_and_self_documents_are_separate_after_html_joining(self):
        parent = parse_passport_documents('부모가 미성년자 여권 신청할 때 준비물', self.body)
        own = parse_passport_documents('만17세 고등학생이 직접 여권 신청할 때 준비물', self.body)
        self.assertIn('법정대리인 동의서', parent)
        self.assertIn('사진 2매', parent)
        self.assertNotIn('인감증명서', parent)
        self.assertNotIn('학생증', parent)
        self.assertIn('인감증명서', own)
        self.assertIn('학생증', own)

    def test_relative_requires_adult_second_degree_and_authorization(self):
        answer = parse_passport_documents('성인 친족이 만17세 자녀 여권 대리 신청 준비물', self.body)
        self.assertIn('만 18세 이상 2촌 이내 친족', answer)
        self.assertIn('위임장', answer)
        self.assertIn('사본가능', answer)

    def test_age_and_role_followups_keep_the_renewal_request(self):
        query = '부모가 청소년 여권 재발급 준비하려는데 서류 알려줘'
        first = build_clarification(query)
        self.assertIn('만 18세 미만', first['answer'])
        resolved = resolve_clarification_reply('만17세야', {'query': query, **first})
        self.assertIsNone(build_clarification(resolved))
        self.assertIn('부모', resolved)
        self.assertIn('재발급', resolved)
        self.assertIn('법정대리인 동의서', parse_passport_documents(resolved, self.body))

    def test_parent_reply_without_age_keeps_asking_age_not_issuing_adult_list(self):
        query = '청소년 여권 준비물'
        first = build_clarification(query)
        resolved = resolve_clarification_reply('부모가 신청할 거야', {'query': query, **first})
        self.assertIn('청소년', resolved)
        self.assertIn('만 18세 미만', build_clarification(resolved)['answer'])
        self.assertIsNone(parse_passport_documents(resolved, self.body))

    def test_explicit_age_is_not_overridden_by_adult_visitor_word(self):
        self.assertEqual(applicant_age('성인 친족이 만17세 아이 여권 대리신청'), 'minor')
        self.assertEqual(applicant_age('18세 고등학생 여권 신청'), 'adult')
        self.assertIsNone(applicant_age('고등학생 직접 여권 신청'))

    def test_legacy_lines_and_edited_source_values_are_read_not_fixed(self):
        plain = re.sub(r'^#{1,6}\s+', '', self.body, flags=re.M)
        changed = plain.replace('사진 2매', '사진 3매')
        self.assertIn('사진 3매', parse_passport_documents('성인 신규 여권 준비물', changed))

    def test_missing_visitor_boundary_abstains_instead_of_mixing_lists(self):
        changed = self.body.replace('미성년자 본인 신청서 :', '확인되지 않은 유형 :')
        self.assertIsNone(parse_passport_documents('부모가 미성년자 여권 준비물', changed))
        self.assertIsNone(parse_passport_documents('성인 여권 재발급 준비물', self.body.replace('유효기간 남은 여권은 지참', '')))

    def test_old_page_abstains_and_does_not_expose_verified_status(self):
        client = Client({'raw_html': HTML, 'last_checked_at': (datetime.now(timezone.utc)-timedelta(days=60)).isoformat()})
        result = answer_passport_documents('성인 여권 재발급 준비물', client)
        self.assertFalse(result['verified'])
        self.assertEqual(result['sources'], [])
        self.assertNotIn('사진 2매', result['answer'])

    def test_current_page_keeps_source_and_folded_full_original(self):
        client = Client({'raw_html': HTML, 'last_checked_at': datetime.now(timezone.utc).isoformat()})
        result = answer_passport_documents('부모가 미성년자 여권 준비물', client)
        self.assertTrue(result['verified'])
        self.assertEqual(client.url, PASSPORT_URL)
        self.assertEqual(result['sources'][0]['url'], PASSPORT_URL)
        self.assertIn('미성년자 본인', result['answer_details'])
        self.assertNotIn('미성년자 본인', result['answer'])

    def test_collection_and_special_applications_do_not_use_visit_application_list(self):
        for q in ('여권 대리 수령 서류', '여권 온라인 재발급 서류', '긴급 여권 서류', '여권 기록증명 서류'):
            self.assertIsNone(answer_passport_documents(q, None))
        self.assertIsNone(parse_passport_documents('부모가 성인 여권 대신 신청 준비물', self.body))


if __name__ == '__main__': unittest.main()
