"""
NER 기반 비정형 PII 탐지/마스킹 모듈
- KoELECTRA NER 모델로 한국어 인명·지명 등 비정형 개인정보 감지
- 정규식으로 잡히지 않는 PII(이름, 상세 주소 등)에 특화
- 정규식 기반 PII 탐지는 chatbot.conversation의 mask_personal_info()가 담당
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# 한국어 NER 모델 (소형, ~50MB, CPU 추론 ~100ms)
# Naver NER 데이터 기반으로 인명/지명/기관/날짜/시간/숫자/금액 등 14개 라벨
NER_MODEL = "Leo97/KoELECTRA-small-v3-modu-ner"

# 마스킹 대상 NER 라벨 → 표시명 매핑
# PS=Person(인명), LC=Location(지명)만 마스킹.
# AF=Artifact, OG=Organization은 제외 — "지하철/버스" 같은 일반 명사가
# AF로 오탐되어 행정 안내(교통 등) 답변이 가려지는 품질 저하를 막기 위함.
# (사하구청, 부산광역시 등 공공기관명도 마스킹되면 답변 품질 저하)
MASK_LABEL_MAP = {
    "PS": "이름",
}

# 마스킹에서 제외할 단어 (공공기관/지역명/행정용어 등 자주 등장하는 공식 명칭)
# - NER이 인명(PS)/지명(LC)으로 오인하기 쉬운 행정 제도·기관·직책 용어를 예외 처리.
#   (예: '옴부즈만'을 사람 이름으로 오인해 답변 전체가 차단되던 엣지 케이스 방지)
SAFE_TOKENS = {
    # 지역/기관명
    "사하구", "사하구청", "부산", "부산광역시", "부산시",
    "대한민국", "한국",
    # 행정 제도·기관·직책 (인명/지명 오탐 방지)
    "옴부즈만", "시민옴부즈만", "감사관", "옴부즈맨",
    "소통감사실", "구청장", "부구청장", "동장", "통장", "이장",
    "주민센터", "행정복지센터", "민원실", "주민자치회", "구의회",
    "보건소", "복지관", "도서관", "문화원", "구민회관",
}


class NERPIIDetector:
    """KoELECTRA 기반 NER PII 탐지기 (싱글턴)"""

    _instance: Optional["NERPIIDetector"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        try:
            from transformers import pipeline
            logger.info(f"NER 모델 로딩 중: {NER_MODEL}")
            self.pipe = pipeline(
                "ner",
                model=NER_MODEL,
                aggregation_strategy="simple",
                device=-1,  # CPU
            )
            self.enabled = True
            logger.info("NER PII 탐지기 초기화 완료")
        except Exception as e:
            logger.warning(f"NER 모델 로딩 실패 - NER 차단 비활성화 (정규식만 동작): {e}")
            self.pipe = None
            self.enabled = False

        self._initialized = True

    def detect(self, text: str) -> list[dict]:
        """텍스트에서 NER 엔티티 추출. 실패 시 빈 리스트."""
        if not self.enabled or not text:
            return []
        try:
            return self.pipe(text)
        except Exception as e:
            logger.warning(f"NER 추론 실패: {e}")
            return []

    def detect_and_mask(self, text: str) -> tuple[str, list[str]]:
        """
        NER로 비정형 PII 감지 + 마스킹.
        Returns:
            (masked_text, found_label_types)
        """
        if not self.enabled or not text:
            return text, []

        entities = self.detect(text)
        if not entities:
            return text, []

        # 뒤에서부터 치환해야 인덱스가 어긋나지 않음
        entities_sorted = sorted(entities, key=lambda e: e["start"], reverse=True)
        masked = text
        found_types: list[str] = []

        for ent in entities_sorted:
            label = ent.get("entity_group") or ent.get("entity") or ""
            # 라벨 접두사 제거 (B-PS, I-LC → PS, LC)
            label_norm = label.split("-")[-1] if "-" in label else label

            if label_norm not in MASK_LABEL_MAP:
                continue

            word = ent.get("word", "")
            if not word or word in SAFE_TOKENS:
                continue

            # 신뢰도 낮은 매칭 제외 (오탐 방지)
            # 0.75 기준: "홍길동"(0.81), "김철수"(0.98) 등 흔한 이름도 포착
            score = float(ent.get("score", 0))
            if score < 0.75:
                continue

            display = MASK_LABEL_MAP[label_norm]
            start, end = ent["start"], ent["end"]
            masked = masked[:start] + f"[MASKED:{display}]" + masked[end:]
            found_types.append(display)

        return masked, found_types
