"""외부 API 없이 실행되는 개인정보 탐지·마스킹 로직."""

import logging
import re

logger = logging.getLogger(__name__)

PERSONAL_INFO_PATTERNS = [
    (re.compile(r"\d{6}[-\s]?\d{7}"), "주민등록번호"),
    (re.compile(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}"), "전화번호"),
    (re.compile(r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"), "카드번호"),
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "이메일"),
]

ADDRESS_PATTERNS = [
    re.compile(r"[가-힣]{1,20}(?:동|읍|면|리)\s*\d{1,4}(?:-\d{1,4})?(?:\s*(?:번지|호|층))?"),
    re.compile(r"[가-힣]{1,20}(?:로|길)\s*\d{1,4}(?:-\d{1,4})?(?:\s*(?:번지|호|층))?"),
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
