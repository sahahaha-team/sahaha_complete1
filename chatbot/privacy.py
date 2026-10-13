"""외부 API 없이 실행되는 개인정보 탐지·마스킹 로직."""

import logging
import re
from urllib.parse import urlparse, parse_qsl

logger = logging.getLogger(__name__)

PERSONAL_INFO_PATTERNS = [
    (re.compile(r"\d{6}[-\s]?\d{7}"), "주민등록번호"),
    (re.compile(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}"), "전화번호"),
    (re.compile(r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"), "카드번호"),
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "이메일"),
]

ADDRESS_PATTERNS = [
    # Numbers followed by an age/duration/count are not lot numbers. Without
    # this boundary '있으면 65세', '빌리면 2시간' matched the 면/리 suffix.
    re.compile(r"[가-힣]{1,20}(?:동|읍|면|리)\s*\d{1,4}(?:-\d{1,4})?(?!\d|\s*(?:세|시간|분|초|만원|원|회|개월|년|월|일|권|개|명|퍼센트|%))(?:\s*(?:번지|호|층))?"),
    re.compile(r"[가-힣]{1,20}(?:로|길)\s*\d{1,4}(?:-\d{1,4})?(?!\d|\s*(?:세|시간|분|초|만원|원|회|개월|년|월|일|권|개|명|퍼센트|%))(?:\s*(?:번지|호|층))?"),
]


def detect_personal_info(text: str, use_ner: bool = True) -> str | None:
    for pattern, info_type in PERSONAL_INFO_PATTERNS:
        if pattern.search(text):
            return info_type
    for pattern in ADDRESS_PATTERNS:
        if pattern.search(text):
            return "주소"
    if use_ner:
        try:
            from chatbot.pii_detector import NERPIIDetector
            _, found = NERPIIDetector().detect_and_mask(text)
            if found:
                return found[0]
        except Exception as exc:
            logger.warning("NER 탐지 호출 실패 (정규식만 사용): %s", exc)
    return None


def mask_personal_info(text: str, use_ner: bool = True) -> tuple[str, list[str]]:
    found: list[str] = []
    masked = text
    for pattern, info_type in PERSONAL_INFO_PATTERNS:
        if pattern.search(masked):
            found.append(info_type)
            masked = pattern.sub(f"[MASKED:{info_type}]", masked)
    if use_ner:
        try:
            from chatbot.pii_detector import NERPIIDetector
            masked, ner_found = NERPIIDetector().detect_and_mask(masked)
            found.extend(ner_found)
        except Exception as exc:
            logger.warning("NER 마스킹 호출 실패 (정규식 결과만 반환): %s", exc)
    return masked, found


def mask_answer(text: str) -> tuple[str, list[str]]:
    """Keep numeric identifiers in official page/file URLs, mask all prose.

    Only known administrative identifier query parameters are exempt. A mobile
    number or email in a URL/query string still cannot bypass output masking.
    Input detection is unchanged.
    """
    allowed_params = {'mId', 'mid', 'atchFileId', 'fileSn', 'fileNo', 'nttId', 'nttNo', 'bbsId', 'idx'}
    saved = []
    def protect(match):
        value = match.group(0)
        parsed = urlparse(value)
        host = (parsed.hostname or '').lower()
        if (parsed.scheme != 'https' or not (host == 'saha.go.kr' or host.endswith('.saha.go.kr'))
                or '@' in parsed.netloc or parsed.fragment
                or any(key not in allowed_params for key, _ in parse_qsl(parsed.query))):
            return value
        saved.append(value)
        return f'OFFICIALURLTOKEN{chr(65 + len(saved) - 1)}END'
    protected = re.sub(r'https?://[^\s<>\[\]()`]+', protect, text or '')
    masked, found = mask_personal_info(protected, use_ner=False)
    for index, url in enumerate(saved):
        masked = masked.replace(f'OFFICIALURLTOKEN{chr(65 + index)}END', url)
    return masked, found
