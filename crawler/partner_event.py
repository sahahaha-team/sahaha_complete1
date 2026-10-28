"""Read the labelled Busan calendar body, retaining its original date range."""
import re
from bs4 import BeautifulSoup


def event_calendar_content(html: str) -> str:
    root = BeautifulSoup(html, 'lxml').select_one('.boardView')
    if root is None:
        raise ValueError('공식 행사 본문 구조 확인 불가')
    subject = root.select_one('.form-data-subject')
    period = next((dl.find('dd') for dl in root.select('dl.form-data-info')
                   if dl.find('dt') and dl.find('dt').get_text(strip=True) == 'Period'), None)
    if subject is None or period is None:
        raise ValueError('행사명/기간 필드 누락')
    period_text = ' '.join(period.get_text(' ', strip=True).split())
    if len(re.findall(r'20\d{2}-\d{2}-\d{2}', period_text)) != 2:
        raise ValueError('행사 날짜 범위 확인 불가')
    alt = ' '.join(' '.join(img.get('alt', '').split()) for img in root.select('.se-contents img[alt]'))
    korean = re.search(r'제\s*\d+회\s*[가-힣][가-힣\s]{2,60}?축제', alt)
    title = korean[0] if korean else subject.get_text(' ', strip=True)
    lines = ['## ' + title, '원제: ' + subject.get_text(' ', strip=True), '기간: ' + period_text]
    labels = {'Hours': '행사시간', 'Venue': '장소', 'Hosted by': '주최'}
    for para in root.select('.se-contents p'):
        text = para.get_text(' ', strip=True).lstrip('○ ')
        label, separator, value = text.partition(':')
        if separator and label.strip() in labels:
            lines.append(labels[label.strip()] + ': ' + value.strip())
    venue = re.search(r'(?:^|\d+일간\s+)([가-힣][가-힣 ]{1,40}\s+일원)(?=\s|$)', alt)
    if venue:
        # The Korean venue is copied from the published poster alt, not translated.
        lines = [line for line in lines if not line.startswith('장소:')]
        lines.append('장소: ' + venue[1])
    return '\n'.join(lines)
