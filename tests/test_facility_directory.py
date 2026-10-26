import json
from pathlib import Path
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from chatbot.facility_directory import DIRECTORIES, directory_records, facility_directory
from chatbot.response_helpers import build_contextual_search_query, resolve_clarification_reply

SOURCES=json.loads((Path(__file__).parent/'fixtures/facility_directories_20261026.json').read_text(encoding='utf8'))

class FacilityDirectoryTests(unittest.TestCase):
    def answer(self, query, kind='작은도서관', **overrides):
        row={'url':DIRECTORIES[kind], 'title':kind, 'content':SOURCES[DIRECTORIES[kind]]['body'],
             'last_checked_at':datetime.now(timezone.utc).isoformat(), **overrides}
        with patch('database_db.raw_pages.read_raw_pages',return_value=[row]):
            return facility_directory(query,object())

    def test_directory_rows_do_not_borrow_loan_eligibility_or_public_library(self):
        records=directory_records(SOURCES[DIRECTORIES['작은도서관']]['body'],'작은도서관')
        self.assertEqual(len(records),14)
        r=self.answer('하단동 작은도서관 위치와 전화번호')
        for t in ('노을나루길','하신번영로 388','051-220-5207'):
            self.assertIn(t,r['answer'])
        for t in ('부산시 거주자','대출','220-0184'):
            self.assertNotIn(t,r['answer'])

    def test_missing_region_clarifies_then_short_reply_and_correction_replace_region(self):
        result=self.answer('작은도서관 교육 장소는 어디야')
        self.assertTrue(result['is_clarification'])
        query=resolve_clarification_reply('하단동',{**result,'query':'작은도서관 교육 장소는 어디야'})
        r=self.answer(query)
        self.assertIn('노을나루길',r['answer'])
        self.assertIn('모집공고',r['answer'])
        query=build_contextual_search_query('그럼 전화번호는?',[{'role':'user','content':query}])
        self.assertIn('051-220-5207',self.answer(query)['answer'])
        query=build_contextual_search_query('아니 감천2동이에요',[{'role':'user','content':query}])
        self.assertNotIn('하단동',query)
        self.assertIn('051-203-0543',self.answer(query)['answer'])

    def test_health_followup_uses_owned_address_and_phone_without_inventing_prefix(self):
        result=self.answer('근처 마을건강센터 어디야','마을건강센터')
        self.assertTrue(result['is_clarification'])
        query=resolve_clarification_reply('괴정2동',{**result,'query':'근처 마을건강센터 어디야'})
        r=self.answer(query,'마을건강센터')
        self.assertIn('까치고개로 14-1',r['answer'])
        query=build_contextual_search_query('전화번호는?',[{'role':'user','content':query}])
        r=self.answer(query,'마을건강센터')
        self.assertIn('220-5051~2',r['answer'])
        self.assertNotIn('051-',r['answer'])

    def test_unlisted_exact_region_is_not_a_neighbouring_branch(self):
        r=self.answer('하단1동 작은도서관 위치')
        self.assertEqual(r['evidence']['status'],'insufficient')
        self.assertNotIn('노을나루길',r['answer'])

    def test_specific_service_or_other_fields_do_not_take_directory_shortcut(self):
        for query in ('작은도서관 전화번호', '하단동 작은도서관 팩스번호',
                      '하단동 작은도서관 위치와 운영시간','하단동 작은도서관 예약 방법과 위치',
                      '하단동 작은도서관 담당자 전화번호'):
            self.assertIsNone(self.answer(query))
        self.assertIsNone(self.answer('괴정2동 마을건강센터 예방접종 장소','마을건강센터'))
        self.assertIsNone(self.answer('하단동 작은도서관 위치',last_checked_at='2020-01-01T00:00:00Z'))

    def test_conflicting_duplicate_or_broken_owner_cannot_publish_a_phone(self):
        body=SOURCES[DIRECTORIES['작은도서관']]['body']
        fragment='\n작은도서관 — 도서관: 하단2동 노을나루길 작은도서관\n작은도서관 — 주소: 다른 주소\n작은도서관 — 전화번호: 051-999-9999\n'
        body=body.replace('#### 대상',fragment+'#### 대상')
        records=directory_records(body,'작은도서관')
        self.assertFalse(any('노을나루길' in r['name'] for r in records))
        broken='#### 통합대출 참여도서관\n작은도서관 — 도서관: 시험 작은도서관\n공공도서관 — 주소: 다른 시설\n공공도서관 — 전화번호: 051-999-9999'
        self.assertEqual(directory_records(broken,'작은도서관'),[])

if __name__=='__main__': unittest.main()
