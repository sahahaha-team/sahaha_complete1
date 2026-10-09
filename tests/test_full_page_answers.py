import unittest
from chatbot.source_text import clean_source_text
from chatbot.page_answers import select_sections, page_brief
from crawler.page_sections import extract_sections
from chatbot.response_helpers import build_clarification


class FullPageAnswerTests(unittest.TestCase):
    def test_controls_alone_never_become_an_administrative_answer(self):
        self.assertEqual(clean_source_text('열기 블로그 인스타그램 페이스북 카카오 닫기 인쇄하기'), '')
        self.assertEqual(clean_source_text('Home\n민원\n인쇄하기\n실제 행정 안내입니다.\n만족도조사\n매우만족'), '실제 행정 안내입니다.')

    def test_nested_eligibility_keeps_the_program_name(self):
        result = extract_sections('<main><h3>사업 가</h3><h4>지원대상</h4><p>첫 사업의 지원 대상입니다.</p>'
                                  '<h3>사업 나</h3><h4>지원대상</h4><p>둘째 사업의 지원 대상입니다.</p></main>')
        self.assertEqual([r['heading'] for r in result], ['사업 가 / 지원대상', '사업 나 / 지원대상'])

    def test_explicit_food_waste_question_selects_dewatering_instruction(self):
        sections = [{'heading': '음식물쓰레기의 정의', 'text': '음식물쓰레기는 일상생활의 식사 준비 과정에서 발생한 쓰레기를 말합니다.'},
                    {'heading': '음식물쓰레기 배출요령', 'text': '음식물쓰레기는 이물질과 물기를 제거한 후 전용용기에 넣어 배출하여야 합니다.'}]
        body, _ = select_sections('음식물쓰레기는 물기를 빼고 버려야 하나요?', '', sections,
                                  {'음식물', '쓰레기'}, ['음식물', '쓰레기', '물기', '빼다', '버리다'])
        self.assertIn('물기를 제거', body)
        self.assertNotIn('정의', body)

    def test_complete_fields_do_not_trigger_an_unnecessary_scope_question(self):
        body = '신청대상\n관내 등록 임산부가 신청할 수 있습니다.\n구비서류\n신분증과 임신확인서를 지참하세요.'
        self.assertEqual(page_brief('임산부 등록은 누가 할 수 있고 무엇을 가져가야 하나요?', body, '임산부 등록'), body)

    def test_short_numeric_field_is_preserved_with_eligibility(self):
        sections = [{'heading': '청년 지원 / 지원대상', 'text': '지역에 거주하는 청년이며 소득인정액이 선정기준 이하인 사람'},
                    {'heading': '청년 지원 / 선정기준', 'text': '1인 : 140만원'}]
        body, _ = select_sections('청년 지원 신청 조건', '', sections, {'청년'}, ['청년', '지원', '신청', '조건'])
        self.assertIn('140만원', body)

    def test_complete_source_program_outranks_a_budget_mention(self):
        from chatbot.page_index import OfficialPageIndex
        import re
        def tokenize(text): return re.findall(r'[가-힣A-Za-z]+', text)
        rows = [
            {'url': 'https://www.saha.go.kr/portal/contents.do?mId=a', 'title': '청년주거비', 'content': '청년주거비 신청대상은 관내에 거주하는 청년입니다. 신청서와 소득 증빙을 제출합니다.'},
            {'url': 'https://www.saha.go.kr/files/budget.pdf', 'title': '결산서', 'content': '청년주거비 청년주거비 청년주거비 집행금액과 예산 집행 실적에 관한 자료입니다.'},
            {'url': 'https://www.saha.go.kr/portal/contents.do?mId=b', 'title': '도서대출', 'content': '도서관 대출은 회원증을 발급한 뒤 이용할 수 있습니다. 반납일은 대출일에 안내합니다.'},
        ]
        index = OfficialPageIndex(rows, {}, tokenize)
        found = index.search('청년주거비 신청대상', {'청년주거비'})
        self.assertIn('mId=a', found[0]['metadata']['url'])

    def test_specific_passport_questions_and_child_program_are_not_generic_requests(self):
        for question in ('여권 영문성명은 어떻게 표기하나요?', '여권은 주소지와 관계없이 신청할 수 있나요?',
                         '아이 국가예방접종은 어디에서 받을 수 있나요?'):
            self.assertIsNone(build_clarification(question))

    def test_publication_date_is_not_the_appeal_period(self):
        fields = [{'heading': '주택가격 / 결정·공시일', 'text': '1월 1일 기준 : 매년 4월말\n6월 1일 기준 : 매년 9월말'},
                  {'heading': '주택가격 / 이의신청기간', 'text': '공시일로부터 30일간 의견을 제출합니다.'}]
        body, _ = select_sections('주택가격은 언제 공시되나요?', '', fields, {'주택가격'}, ['주택가격', '언제', '공시'])
        self.assertIn('매년 4월말', body)
        self.assertNotIn('30일간', body)

    def test_general_service_does_not_choose_an_unasked_fee(self):
        fields = [{'heading': '진료 / 만성질환 1차진료', 'text': '고혈압\n당뇨\n고지혈증\n감기'},
                  {'heading': '진료 / 진료비', 'text': '65세 이상 거주자 무료, 그 외 대상자는 진료비를 부담합니다.'}]
        body, _ = select_sections('어떤 진료를 받을 수 있나요?', '', fields, {'진료'}, ['진료', '받다'])
        self.assertIn('고혈압', body)
        self.assertNotIn('진료비', body)

    def test_the_full_page_root_does_not_hide_its_relevant_field(self):
        fields = [{'heading': '공식 서비스', 'text': ('일반적인 소개 문장입니다.\n' * 60)},
                  {'heading': '공식 서비스 / 신청방법', 'text': '신분증을 지참하고 센터에 방문하여 신청서를 제출합니다.'}]
        body, _ = select_sections('공식 서비스 신청방법', '', fields, {'서비스'}, ['신청', '방법'])
        self.assertIn('신분증을 지참', body)
        self.assertLess(len(body), 300)

    def test_council_alias_does_not_displace_the_canonical_page(self):
        from chatbot.page_index import OfficialPageIndex
        rows = [{'url': f'https://{host}/portal/contents.do?mId=x', 'title': '공식교육 안내',
                 'content': '공식교육은 관내 주민을 대상으로 운영하며 주민 누구나 교육을 신청할 수 있습니다.'}
                for host in ['tour.saha.go.kr', 'www.saha.go.kr']]
        index = OfficialPageIndex(rows, {}, lambda text: text.split())
        self.assertEqual(len(index.rows), 1)
        self.assertIn('www.saha.go.kr', index.rows[0]['metadata']['url'])

    def test_named_subprogram_cannot_use_another_programs_amount(self):
        fields = [{'heading': '가족지원 / 아기바우처', 'text': '첫째 200만원, 둘째 이후 300만원을 지급합니다.'},
                  {'heading': '가족지원 / 산후조리비 / 지원금액', 'text': '산후조리비는 100만원 한도로 지원합니다.'}]
        body, _ = select_sections('아기바우처는 얼마인가요?', '', fields, {'아기바우처'}, ['아기바우처', '얼마'])
        self.assertIn('300만원', body)
        self.assertNotIn('산후조리비', body)

    def test_legacy_headings_still_keep_named_programs_separate(self):
        fields = [{'heading': '아기바우처', 'text': '첫째 200만원, 둘째 이후 300만원을 지급합니다.'},
                  {'heading': '산후조리비 지원금액', 'text': '산후조리비는 100만원 한도로 지원합니다.'}]
        body, _ = select_sections('아기바우처는 얼마인가요?', '', fields, {'아기바우처'}, ['아기바우처', '얼마'])
        self.assertIn('300만원', body)
        self.assertNotIn('산후조리비', body)

    def test_service_routing_uses_full_page_before_chunks(self):
        from unittest.mock import Mock
        from chatbot.retriever import HybridRetriever
        retriever = object.__new__(HybridRetriever)
        url = 'https://www.saha.go.kr/portal/contents.do?mId=service'
        page = {'content': '사업의 신청 조건과 구비서류 전체 안내', 'metadata': {'url': url, 'page_document': True}}
        retriever.bm25 = Mock()
        retriever.bm25.pages.rows = [page]
        retriever.bm25._tokenize.return_value = ['구비서류']
        retriever.db = Mock()
        found = retriever.search_official_url('구비서류', url)
        self.assertTrue(found['results'][0]['metadata']['page_document'])
        retriever.db.client.table.assert_not_called()

    def test_consequences_question_does_not_choose_payment_instructions(self):
        fields = [{'heading': '체납 / 납부안내', 'text': '고지서를 지참하여 금융기관에서 납부합니다.'},
                  {'heading': '체납 / 불이익', 'text': '재산 압류 및 자동차 번호판 영치, 관허사업 제한 등의 불이익이 있습니다.'}]
        body, _ = select_sections('지방세를 내지 않으면 어떤 불이익이 있나요?', '', fields, {'지방세', '체납'}, ['지방세', '체납'])
        self.assertIn('재산 압류', body)
        self.assertNotIn('금융기관', body)

    def test_conflicting_source_thresholds_are_not_presented_as_one_rule(self):
        body = ('지원대상 : 소득인정액이 선정기준 이하인 가구\n'
                '선정기준 : 급여종류별 기준 충족 → 부양의무자의 소득 연 1.3억원·일반재산 12억원\n'
                '개정사항 : 고소득(연1억) ·고재산(9억) 부양의무자')
        brief = page_brief('수급자 선정기준', body, '공식 안내')
        self.assertIn('서로 다르게', brief)
        self.assertNotIn('1.3억원', brief)

    def test_counseling_place_request_prefers_booking_and_address(self):
        from chatbot.question_intent import asks_location
        question = '정신건강 상담받을 곳이 있나요?'
        self.assertTrue(asks_location(question))
        fields = [{'heading': '정신건강 / 센터 운영', 'text': '정신건강 상담을 원하는 주민에게 서비스를 제공합니다.'},
                  {'heading': '정신건강 / 이용 안내', 'text': '위치 : 장림번영로 41\n이용방법 : 사전 전화예약 필수'}]
        body, _ = select_sections(question, '', fields, {'정신건강'}, ['정신건강', '상담'])
        self.assertIn('사전 전화예약', body)

    def test_online_service_page_outranks_an_incidental_fee_table(self):
        from chatbot.page_index import OfficialPageIndex
        rows = [{'url': 'https://www.saha.go.kr/health/contents.do?mId=fee', 'title': '증명 발급 수수료',
                 'content': '검사확인서 발급 수수료와 처리기간, 신분증 등 구비서류를 안내하는 공식 표입니다.'},
                {'url': 'https://www.saha.go.kr/health/contents.do?mId=online', 'title': '증명 온라인발급',
                 'content': '검사확인서는 검사 결과 정상인 경우 온라인 공공보건포털에서 발급받을 수 있습니다.'},
                {'url': 'https://www.saha.go.kr/portal/contents.do?mId=other', 'title': '도서관 이용',
                 'content': '도서관에서는 주민을 위한 책과 다양한 독서 문화 활동을 제공하며 회원 누구나 참여합니다.'}]
        import re
        index = OfficialPageIndex(rows, {}, lambda text: re.findall(r'검사확인서|온라인|발급', text) + text.split())
        found = index.search('검사확인서를 온라인 발급할 수 있나요?', {'검사확인서'})
        self.assertIn('mId=online', found[0]['metadata']['url'])

    def test_same_field_in_new_document_version_remains_available(self):
        from chatbot.bm25_index import page_sections_by_url
        rows = [dict(url='official', section_heading='선정기준', section_text='동일한 선정기준', content_hash=version)
                for version in ('old', 'current', 'current')]
        self.assertEqual([s['hash'] for s in page_sections_by_url(rows)['official']], ['old', 'current'])

    def test_search_loading_uses_primary_key_cursor_instead_of_shifting_offsets(self):
        from chatbot.bm25_index import read_search_documents
        from unittest.mock import Mock
        client = Mock()
        query = client.table.return_value.select.return_value.order.return_value.limit.return_value
        query.gt.return_value = query
        query.execute.side_effect = [Mock(data=[{'id':f'{i:04d}'} for i in range(1000)]), Mock(data=[{'id':'last'}])]
        rows = read_search_documents(client)
        self.assertEqual(len(rows),1001)
        query.gt.assert_called_once_with('id','0999')
        client.table.return_value.select.return_value.order.assert_called_with('id')
        query.range.assert_not_called()

    def test_duplicate_legacy_field_keeps_its_parent_program(self):
        fields = [{'heading': '사업 소개', 'text': '의료비를 지원하는 사업입니다.'},
                  {'heading': '소아의료비 / 사업 소개', 'text': '의료비를 지원하는 사업입니다.'},
                  {'heading': '소아의료비 / 신청 절차', 'text': '신분증과 신청서를 제출합니다.'}]
        body, _ = select_sections('소아의료비 지원사업은 무엇인가요?', '', fields, {'소아의료비'})
        self.assertIn('의료비를 지원하는 사업', body)

    def test_parent_table_is_not_discarded_because_it_has_child_fields(self):
        fields = [{'heading': '감염병 안내', 'text': '구분 | 제1급 | 제2급\n종류 | 감염병 가 | 감염병 나\n' + '분류에 관한 설명입니다. ' * 45},
                  {'heading': '감염병 안내 / 신고의무자', 'text': '진단한 의료기관의 장은 신고해야 합니다.'}]
        body, _ = select_sections('감염병에는 어떤 종류가 있나요?', '', fields, {'감염병'}, ['감염병', '종류'])
        self.assertIn('종류 | 감염병 가', body)

    def test_resident_safety_question_keeps_household_instructions(self):
        fields = [{'heading': '폭염 / 일반 가정 등에서는', 'text': '야외활동을 자제하고 물을 많이 마시세요.'},
                  {'heading': '폭염 / 산업·건설현장에서는', 'text': '건설기계의 냉각장치를 점검하고 방열막을 설치하세요.'}]
        body, _ = select_sections('폭염특보 때 주민은 어떻게 행동해야 하나요?', '', fields, {'폭염'}, ['폭염', '행동'])
        self.assertIn('물을 많이', body)
        self.assertNotIn('건설기계', body)

    def test_multiple_explicit_program_names_are_not_reduced_to_one(self):
        from chatbot.page_index import OfficialPageIndex
        index = object.__new__(OfficialPageIndex)
        index.subject_names = {'청년주거비', '노인주거비'}
        index.tokenize = lambda text: [text]
        self.assertEqual(index.focus_keywords('청년주거비와 노인주거비 신청', {'주거비'}), {'청년주거비', '노인주거비'})

    def test_validated_full_page_can_answer_with_a_field_without_repeating_its_name(self):
        from chatbot.source_answers import build_source_answer
        from unittest.mock import Mock
        import hashlib
        text = '청년주거비와 노인주거비를 안내합니다.\n결정·공시일\n매년 4월말에 공시합니다.'
        meta = {'url':'https://www.saha.go.kr/portal/contents.do?mId=dates', 'title':'주거비 안내',
                'page_document':True, 'content_hash':hashlib.sha256(text.encode()).hexdigest(),
                'page_sections':[{'heading':'결정·공시일','text':'매년 4월말에 공시합니다.'}]}
        client = Mock()
        client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{'content':text,'title':'주거비 안내'}]
        answer, used = build_source_answer([{'content':text,'metadata':meta}],client,
                                           query='청년주거비와 노인주거비는 언제 공시되나요?', topic_keywords={'청년주거비','노인주거비'})
        self.assertIn('4월말',answer)
        self.assertEqual(len(used),1)

    def test_source_changed_after_indexing_never_reuses_old_numeric_fields(self):
        from chatbot.source_answers import build_source_answer
        from unittest.mock import Mock
        import hashlib
        old = '주거비 지원\n지원금액\n100만원 지원'
        current = '주거비 지원\n지원금액\n200만원 지원으로 변경되었습니다.'
        meta = {'url':'https://www.saha.go.kr/portal/contents.do?mId=changed', 'title':'주거비 지원',
                'page_document':True, 'content_hash':hashlib.sha256(old.encode()).hexdigest(),
                'page_sections':[{'heading':'주거비 지원 / 지원금액','text':'100만원 지원'}]}
        client = Mock()
        client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{'content':current,'title':'주거비 지원'}]
        answer, _ = build_source_answer([{'content':old,'metadata':meta}],client,
                                        query='주거비 지원금액',topic_keywords={'주거비'})
        self.assertIn('200만원',answer)
        self.assertNotIn('100만원',answer)

    def test_age_question_selects_actual_age_criteria_before_service_benefits(self):
        fields = [{'heading':'지원내용','text':'돌보미가 아동의 집으로 찾아가 돌봄서비스를 제공합니다.'},
                  {'heading':'선정기준','text':'대상아동 연령기준 : 생후 3개월~12세 이하 아동\n양육공백 가정이 대상입니다.'},
                  {'heading':'지원대상','text':'돌봄이 필요한 가정이 이용할 수 있습니다.'}]
        body, _ = select_sections('돌봄 지원사업은 몇 살까지 이용할 수 있나요?', '', fields,
                                  {'돌봄'}, ['돌봄','지원','사업','이용'])
        self.assertIn('3개월~12세',body)

    def test_general_tax_owner_question_keeps_multiple_property_types(self):
        fields = [{'heading':'지방세 / 재산세 / 토지','text':'납세의무자 : 매년 6월 1일 현재 토지소유자\n세율 : 토지별 적용'},
                  {'heading':'지방세 / 재산세 / 주택, 건축물','text':'납세의무자 : 매년 6월 1일 현재 사실상 재산을 소유하고 있는 자\n과세대상 : 주택, 건축물, 선박, 항공기'},
                  {'heading':'지방세 / 자동차세','text':'납세의무자 : 자동차 소유자'}]
        body, _ = select_sections('재산세는 어떤 날짜를 기준으로 누가 내나요?', '', fields, {'재산세'})
        self.assertIn('토지소유자',body)
        self.assertIn('사실상 재산',body)
        self.assertNotIn('자동차 소유자',body)


if __name__ == '__main__':
    unittest.main()
