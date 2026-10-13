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
    # Civil-service detail forms are vertical th/td pairs. Their spanning
    # title is a program heading, never a column header on every fact.
    if 'tableSt_view' in (table.get('class') or []):
        output = []
        for row in table.find_all('tr'):
            cells = row.find_all(['th', 'td'], recursive=False)
            if len(cells) == 1 and cells[0].name == 'th' and 'title' in (cells[0].get('class') or []):
                output.append('### ' + _text(cells[0]))
                continue
            if len(cells) % 2 or not all(cells[i].name == 'th' and cells[i+1].name == 'td'
                                      for i in range(0,len(cells),2)):
                return []  # Changed/ambiguous layouts must not swap fields.
            for i in range(0,len(cells),2):
                label = _text(cells[i])
                if label == '첨부파일':
                    continue
                # Retain all numbered document requirements as intact units.
                values = cells[i+1].get_text('\n', strip=True).splitlines()
                output.extend(label + ': ' + ' '.join(v.split()) for v in values if v.strip())
        return output
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
        # Repeated category cells (e.g. 건강돌봄) are not a program identity.
        # Carry the explicit program column on every cell of that same row.
        identity_columns = [c for c, labels in headers.items()
                            if any(re.fullmatch(r'사업명|프로그램명|서비스명|시설명|주차장명|품명', re.sub(r'\s+','',label)) for label in labels)]
        if any(any(re.sub(r'\s+','',label)=='품명' for label in headers[c]) for c in identity_columns):
            identity_columns += [c for c, labels in headers.items() if any(re.sub(r'\s+','',label)=='규격' for label in labels)]
        for column in identity_columns:
            if column < len(row):
                identity = row[column][0]
                if identity and not identity.isdigit() and len(identity)<60 and identity not in row_label:
                    row_label += ' / ' + identity
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
    # Detail forms wrap published facts, while search/input forms are chrome.
    for form in root.select('form'):
        if form.get('id') == 'detailForm' and form.select_one('table.tableSt_view th.title'):
            form.unwrap()
        else:
            form.decompose()
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
            prefix = re.split(r'[▹▷]',value,1)[0].strip()
            if prefix != value and re.search(r'클리닉|상담전화\s*안내',prefix):
                lines.append('#' * int(node.name[1]) + ' ' + prefix)
                lines.append(value)
                field = None
                continue
            # Label headings are fields; program headings retain hierarchy.
            if re.search(r'이란[?？]?$',value):
                field = '정의'
                lines.append('#' * int(node.name[1]) + ' ' + value)
            elif value.endswith(('?', '？')):
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
