"""Event dates belong to the requested event/year, not a page's crawl date."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

EVENT = re.compile(r'축제|박람회|공연|전시회|행사')
HISTORY = re.compile(r'교류|방문\s*(?:기록|실적|이력)|역대|개최\s*실적|연혁|통계|보고서')
YEAR = re.compile(r'(?<!\d)(20\d{2}|\d{2})\s*년(?:도)?(?!째|간|근속)')


def event_years(query: str, current_year: int | None = None) -> set[int]:
    if not EVENT.search(query or '') or HISTORY.search(query or ''):
        return set()
    years = {int(m[1]) if len(m[1]) == 4 else 2000 + int(m[1]) for m in YEAR.finditer(query)}
    if years:
        return years
    now = current_year if current_year is not None else datetime.now(ZoneInfo('Asia/Seoul')).year
    if '재작년' in query: return {now - 2}
    if re.search(r'작년|지난해', query): return {now - 1}
    if '내년' in query: return {now + 1}
    if re.search(r'올해|이번|현재|언제|일정|날짜|기간|몇\s*월', query): return {now}
    return set()


def year_reply(previous: str, reply: str) -> str | None:
    """A bare year correction retains the event, never an unrelated new topic."""
    if not EVENT.search(previous or ''):
        return None
    compact = re.sub(r'[\s?.!？]', '', reply)
    if not re.fullmatch(r'(?:아니(?:요)?|정정)?(?:20\d{2}|\d{2})년(?:도)?'
                        r'(?:(?:거|꺼|걸|것)(?:는|를)?)?(?:말하는(?:거야|거예요)|이야|이에요|예요|은|은요|요)?', compact):
        return None
    base = YEAR.sub('', previous)
    base = re.sub(r'재작년|작년|지난해|올해|이번\s*해|내년', '', base)
    return base.strip() + ' ' + reply


def event_history_source(query: str, title: str, body: str) -> bool:
    if not EVENT.search(query or '') or HISTORY.search(query or ''):
        return False
    headings = '\n'.join(line for line in body.splitlines() if line.startswith('#')
                         or re.fullmatch(r'\s*(?:교류실적|교류현황|자매결연|우호도시)\s*', line))
    return bool(re.search(r'교류실적|교류현황|자매결연|우호도시', title + '\n' + headings)
                and not EVENT.search(title))


def dated_unit_compatible(query: str, unit: str) -> bool:
    wanted = event_years(query)
    years = {int(y) for y in re.findall(r'(?<!\d)(20\d{2})(?=\s*(?:년|[./-]\s*\d))', unit)}
    return not wanted or not years or bool(wanted & years)


def event_source_time(query: str, title: str, body: str) -> bool | None:
    wanted = event_years(query)
    if not wanted:
        return None
    if event_history_source(query, title, body):
        return False
    from chatbot.query_subject import fallback_keywords
    from chatbot.source_scope import normalize_plain_source
    from chatbot.structured_answers import scoped_units
    units = scoped_units(query, normalize_plain_source(body, title), fallback_keywords(query))
    # Only the event's selected section can establish its year. Copyright,
    # update timestamps and a different event's date cannot lend a year.
    facts = '\n'.join(u for u in units if not re.search(r'저작권|copyright|최근업데이트|확인일|갱신일', u, re.I))
    dated_facts = '\n'.join(u for u in facts.splitlines() if not u.startswith(('#', '원제:')))
    date_years = {int(y) for y in re.findall(r'(?<!\d)(20\d{2})(?=\s*(?:년|[./-]\s*\d))', dated_facts)}
    years = date_years or {int(y) for y in re.findall(r'(?<!\d)(20\d{2})(?!\d)', facts)}
    return wanted.issubset(years)
