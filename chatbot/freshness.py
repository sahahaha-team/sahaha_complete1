"""One age policy for raw-page candidates and final source verification."""
from config import SOURCE_DYNAMIC_MAX_AGE_DAYS, SOURCE_MAX_AGE_DAYS


def source_max_age_days(query: str) -> int:
    from chatbot.answer_goal import requested_goals
    dynamic_fields = {'hours', 'location', 'cost', 'schedule', 'eligibility', 'documents', 'conditions'}
    dynamic = bool(dynamic_fields.intersection(requested_goals(query))) or any(
        word in query for word in ('올해', '현재', '최신', '오늘', '지금', '운영', '시간',
            '수수료', '비용', '금액', '요금', '지원금', '기준', '대상', '기간', '언제',
            '전화', '연락처', '담당', '주소', '위치', '얼마', '몇 시'))
    return SOURCE_DYNAMIC_MAX_AGE_DAYS if dynamic else SOURCE_MAX_AGE_DAYS
