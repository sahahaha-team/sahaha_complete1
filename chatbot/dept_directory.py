"""
사하구청 부서명 보정 + 담당부서 연락처 디렉터리

목적:
- LLM이 출력하는 부서명 오기를 공식 조직도 명칭으로 보정
  (예: '도로과' → '도로정비과'). 미팅 피드백 반영.
- 출처 카드에 '담당 부서명(과) + 연락처'를 함께 제시하기 위한 연락처 매핑.

주의(사실 기반 원칙):
- 연락처는 확인된 공식 번호만 등재한다. 모르면 비워 두고 대표전화로 폴백한다.
  (없는 번호를 지어내면 환각이 되어 신뢰성을 해친다)
- 부서명 보정/연락처는 공식 홈페이지 조직도를 기준으로 점진 확장한다.
"""

import re

# 사하구청 대표전화 (부서 직통번호를 모를 때 폴백)
REP_PHONE = "051-220-4000"

# 부서명 오기 → 공식 명칭 보정 (공식 조직도 기준으로만 등재)
# key가 답변/메타데이터에 그대로 등장하면 value로 치환한다.
DEPT_CORRECTIONS = {
    "도로과": "도로정비과",
}

# 담당부서 → 직통 연락처 (확인된 공식 번호만. 미확인 부서는 등재하지 않음)
# 형식: "공식부서명": "전화번호"
DEPT_CONTACTS: dict[str, str] = {
    # 예) "소통감사실": "051-220-xxxx",  ← 공식 번호 확인 후 등재
}

# 보정 사전을 정규식으로 미리 컴파일 (긴 key 우선 매칭으로 부분치환 방지)
_CORRECTION_PATTERN = (
    re.compile("|".join(re.escape(k) for k in sorted(DEPT_CORRECTIONS, key=len, reverse=True)))
    if DEPT_CORRECTIONS else None
)


def correct_dept(name: str) -> str:
    """단일 부서명 문자열을 공식 명칭으로 보정 (매칭 없으면 원본 반환)."""
    if not name:
        return name
    return DEPT_CORRECTIONS.get(name.strip(), name.strip())


def normalize_dept_names(text: str) -> str:
    """본문(답변) 내 부서명 오기를 일괄 보정."""
    if not text or _CORRECTION_PATTERN is None:
        return text
    return _CORRECTION_PATTERN.sub(lambda m: DEPT_CORRECTIONS[m.group(0)], text)


def get_contact(dept: str) -> str:
    """
    부서 직통 연락처 반환. 확인된 번호가 없으면 대표전화로 폴백.
    (보정 후 공식명 기준으로 조회)
    """
    if not dept:
        return REP_PHONE
    return DEPT_CONTACTS.get(correct_dept(dept), REP_PHONE)
