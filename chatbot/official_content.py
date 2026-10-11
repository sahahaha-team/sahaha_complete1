"""Preserve official HTML headings, list fields and table cell ownership.

Only the content container is read. Neither captions nor navigation are facts.
Row/column spans are expanded before labelling values, so an age range or price
cannot silently become the answer for an adjacent program.
"""
from __future__ import annotations

import re
from functools import lru_cache
from bs4 import BeautifulSoup, Tag
from chatbot.answer_completion import sentence_complete, source_unit_complete


def _text(node: Tag) -> str:
    return ' '.join(node.get_text(' ', strip=True).split())


def table_units(table: Tag) -> list[str]:
    grid, spans = [], {}
    for row_index, row in enumerate(table.find_all('tr')):
        cells, column = {}, 0
        for (r, c), value in spans.items():
            if r == row_index:
                cells[c] = value
        for cell in row.find_all(['th', 'td'], recursive=False):
            while column in cells:
                column += 1
            value = _text(cell)
            try:
                width, height = int(cell.get('colspan', 1)), int(cell.get('rowspan', 1))
            except ValueError:
                return []
            if not 1 <= width <= 30 or not 1 <= height <= 200:
                return []
            for delta in range(width):
                cells[column + delta] = (value, cell.name == 'th')
                for down in range(1, height):
                    spans[row_index + down, column + delta] = (value, cell.name == 'th')
            column += width
        grid.append([cells.get(i, ('', False)) for i in range(max(cells, default=-1) + 1)])
    if not grid:
        return []
    headers = {}
    output = []
    for row in grid:
        # Column headings have no data cells. Row headings remain with values.
        if row and all(is_header for _, is_header in row) and len(row) > 2:
            for column, (value, _) in enumerate(row):
                if value and value not in headers.get(column, []):
                    headers.setdefault(column, []).append(value)
            continue
        if not any(value for value, _ in row):
            continue
        row_label = row[0][0] if len(row) > 2 or (row and row[0][1]) else ''
        fields = []
        for column, (value, is_header) in enumerate(row):
            if not value or (column == 0 and row_label):
                continue
            label = ' / '.join(headers.get(column, []))
            # Vertical key/value tables sometimes use td for both columns.
            if len(row) == 2 and not headers:
                fields = [row[0][0] + ': ' + row[1][0]]
                break
            field = f'{label}: {value}' if label else value
            fields.append(field)
        if fields:
            prefix = row_label + ' — ' if row_label and headers else ''
            labels = ' '.join(' '.join(h) for h in headers.values())
            if re.search(r'시설명|소재지|사무소명', labels) and len(' · '.join(fields)) < 300:
                output.append(prefix + ' · '.join(fields))
            else:
                output.extend(prefix + f for f in fields)
    return output


@lru_cache(maxsize=32)
def official_html_text(html: str) -> str | None:
    if not html:
        return None
    soup = BeautifulSoup(html, 'lxml')
    root = soup.select_one('#conts, .board_view, article')
    if root is None:
        return None
    for node in root.select('script,style,nav,form,.offscreen,.hidden,.tableSt_list,.bbs_search,.satisfaction,.tabSt,.tab_menu,.tab_wrap'):
        node.decompose()
    title = soup.select_one('#contents h2, h2.title, .cont_title h2, .sub_title h2')
    lines = ['## ' + _text(title)] if title else []
    field = None
    for node in root.find_all(['h2','h3','h4','h5','h6','p','li','table','dt','dd','div']):
        if node.name == 'div' and node.find(['h2','h3','h4','h5','h6','p','li','table','dt','dd','div','script']):
            continue
        if node.find_parent('table') is not None:
            continue
        if node.name == 'table':
            lines.extend(table_units(node))
            field = None
            continue
        if node.find_parent(['li','p','dd']) is not None:
            continue
        value = _text(node)
        if not value or value in ('게시판 목록', '인쇄하기'):
            continue
        if node.name.startswith('h'):
            # Label headings are fields; program headings retain hierarchy.
            if value.endswith(('?', '？')):
                field = '정의' if re.search(r'란\??$|는\?$', value) else None
                lines.append('#' * int(node.name[1]) + ' ' + value)
            elif (sentence_complete(value)
                  or (source_unit_complete(value) and (len(value) >= 45
                      or re.search(r'\d+.*(?:제공|지원|운영|등록|예약)$', value)))
                  or re.search(r'(?:말 것|할 것|피할 것)(?:\s*-.*)?$', value)):
                field = None
                lines.append(value)
            elif re.fullmatch(r'(?:지원|진료|사업|운영|신청|접수|이용|교육|검사|검진|상담|표기)?\s*(?:대상|내용|방법|기간|시간|장소|자격|조건)|처리업무|준비물|구비\s*서류|지원\s*대상|지원\s*내용|지참물|신고시\s*제출서류|만성질환\s*1차진료|(?:대상자\s*)?선정\s*기준', value):
                field = value.replace(' ', '')
                if re.search(r'진료$', value):
                    field = '진료내용'
                if re.search(r'선정\s*기준$',value):
                    field = '선정기준'
                lines.append('#' * int(node.name[1]) + ' ' + value)
            elif re.search(r'(?:기준|조건)\s*[▷▹]\s*\S', value):
                field = None
                lines.append(re.sub(r'^\d+[.]\s*', '', value).replace('▷', ':').replace('▹', ':'))
            elif ':' in value or '：' in value:
                field = None
                label = re.split(r'[:：]', value, maxsplit=1)[0].strip()
                if re.search(r'(?:가전|클리닉|프로그램|지원사업|센터)$', label):
                    lines.append('#' * int(node.name[1]) + ' ' + label)
                lines.append(value)
            else:
                field = '감경내용' if value.endswith('감경') else None
                lines.append('#' * int(node.name[1]) + ' ' + value)
        else:
            # Nested lists belong to their outer label. get_text joins wrapped
            # age ranges and link text without removing any source condition.
            if node.find(['table','h2','h3','h4','h5','h6']):
                continue  # Descendants are read separately with their own ownership.
            if field and not re.match(r'^[^:：]{1,30}[:：]', value):
                value = field + ': ' + value
            elif (field and re.fullmatch(r'(?:지원|진료|운영|사업|서비스)?내용', field)
                  and not re.match(re.escape(field) + r'\s*[:：]', value)):
                # A benefit item can have its own colon inside the parent
                # support-content field (e.g. child allowance: amount).
                value = field + ': ' + value
            elif re.match(r'^신고시 제출서류 ', value):
                value = value.replace('신고시 제출서류 ', '신고시 제출서류: ', 1)
            lines.append(value)
    return '\n'.join(lines).strip() or None
