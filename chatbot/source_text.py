"""Remove page controls without changing administrative source sentences."""
import re


def clean_source_text(text: str) -> str:
    text = (text or '').replace('\r', '')
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in text.splitlines()]
    # The complete page has breadcrumbs before the print control. A section
    # containing only controls must become empty, not an official answer.
    if '인쇄하기' in lines:
        lines = lines[lines.index('인쇄하기') + 1:]
    for index, line in enumerate(lines):
        if line in ('만족도조사', '이 페이지에서 제공하는 정보에 만족하십니까?'):
            lines = lines[:index]
            break
    controls = {'Home', 'HOME', '>', '열기', '닫기', '블로그', '인스타그램',
                '페이스북', '카카오', '인쇄하기', '공유하기', '글자크기', '본문 바로가기'}
    return '\n'.join(line for line in lines if line and line not in controls
                     and not all(word in controls for word in line.split())).strip()


def substantive_source(text: str) -> bool:
    value = clean_source_text(text)
    return len(value) >= 35 and not bool(re.fullmatch(r'[가-힣A-Za-z ·|/]+', value))
