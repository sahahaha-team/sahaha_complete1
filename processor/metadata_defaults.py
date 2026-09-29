"""외부 LLM 없이 메타데이터 누락을 보완하는 순수 함수."""

import re
from collections import Counter

_KEYWORD_STOPWORDS = {
    "그리고", "또한", "대한", "관련", "경우", "통해", "위한", "있는", "하는",
    "합니다", "됩니다", "안내", "사하구", "사하구청", "부산광역시", "페이지",
}


def fallback_keywords(text: str, title: str = "", limit: int = 5) -> list[str]:
    """LLM 태깅 실패 시에도 비어 있지 않은 설명 가능한 키워드를 만든다."""
    tokens = re.findall(r"[가-힣A-Za-z]{2,}", f"{title} {text}")
    counts = Counter(token for token in tokens if token not in _KEYWORD_STOPWORDS)
    return [token for token, _ in counts.most_common(limit)]
