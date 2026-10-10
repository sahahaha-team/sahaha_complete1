"""Add a little practical guidance from the same verified service section."""
from __future__ import annotations

import re

from chatbot.answer_completion import source_unit_complete, QUALIFICATION, can_continue
from chatbot.answer_goal import answer_goal, requested_goals
from chatbot.query_subject import compact, substantive_keywords
from chatbot.question_intent import location_source_units, has_location_unit, has_opening_hours


def _kind(unit: str) -> str | None:
    if has_opening_hours(unit):
        return 'hours'
    if has_location_unit(unit):
        return 'location'
    if re.match(r'^(?:신청|접수|등록|이용|예약)방법\s*[:：]', unit):
        return 'method'
    if (re.match(r'^(?:운영|사업|서비스|진료|지원|상담)내용\s*[:：]', unit)
            or ('상담' in unit and any(word in unit for word in ('지원', '제공', '보조제')))
            or ('서비스' in unit and '제공' in unit)):
        return 'services'
    return None


def enrich_answer(query: str, answer: str, body: str, keywords: set[str], title: str = '') -> str:
    from chatbot.concise_answers import _source_units, section_bounds, condition_indices, MAX_BRIEF_LENGTH

    goals = requested_goals(query)
    if answer_goal(query) == 'reference':
        return answer
    units = _source_units(location_source_units(body.splitlines()))
    answered = compact(answer)
    anchors = [i for i, unit in enumerate(units)
               if len(compact(unit)) >= 8 and source_unit_complete(unit) and compact(unit) in answered]
    if not anchors:
        return answer
    regions = {section_bounds(units, i) for i in anchors}
    if len(regions) != 1:
        return answer
    start, end = regions.pop()
    anchor = anchors[0]

    def safe(index):
        unit = units[index]
        return (source_unit_complete(unit) and not QUALIFICATION.match(unit)
                and not re.search(r'예정|미정|추후|잠정', unit)
                and not any(u == '[…]' for u in units[min(index, anchor):max(index, anchor) + 1])
                and not (index > start and can_continue(units[index - 1])))

    def append(index, *, usage=False):
        nonlocal answer, answered
        selected = condition_indices(units, [index])
        # A youth/reservation condition can precede the target row in an
        # official table. Keep that restriction with any usage guidance.
        if usage:
            selected += [i for i in range(start, end) if re.search(
                r'예약\s*(?:필수|필요)|사전\s*예약.*(?:필수|필요)|반드시.*예약', units[i])]
        additions = []
        for i in sorted(set(selected)):
            unit = units[i]
            if not source_unit_complete(unit):
                return False
            if compact(unit) not in answered:
                additions.append('- ' + unit)
        if not additions:
            return False
        candidate = answer + '\n' + '\n'.join(additions)
        if len(candidate) > MAX_BRIEF_LENGTH:
            return False
        answer, answered = candidate, compact(candidate)
        return True

    # Requested fields have priority over optional detail. Do not substitute
    # an institution's name or a phone number for its actual address/hours.
    missing = []
    for goal in goals:
        checker = has_location_unit if goal == 'location' else has_opening_hours if goal == 'hours' else None
        if checker is None or any(checker(line.removeprefix('- ').strip()) for line in answer.splitlines()):
            continue
        candidates = [i for i in range(start, end) if safe(i) and checker(units[i])]
        distinct = {compact(units[i]): i for i in candidates}
        if len(distinct) == 1:
            if not append(next(iter(distinct.values())), usage=True):
                missing.append(goal)
        else:
            missing.append(goal)
    for goal in missing:
        label = '위치' if goal == 'location' else '운영시간'
        note = f'\n{label}는 이 자료에서 명확히 확인되지 않았습니다.'
        if len(answer) + len(note) <= MAX_BRIEF_LENGTH:
            answer += note

    # Enrich audience/service questions only when a named service is clear.
    # Generic portals, repeated targets and multi-column tables stay narrow.
    if len(goals) > 1 or answer_goal(query) not in ('eligibility', 'services'):
        return answer
    topics = substantive_keywords(keywords) - {'보건소', '구청'}
    heading = compact(title + ' ' + units[start])
    if not topics or not all(word in heading for word in topics):
        return answer
    priorities = ({'services': 30, 'method': 20, 'location': 15, 'hours': 10}
                  if answer_goal(query) == 'eligibility'
                  else {'method': 30, 'location': 20, 'hours': 15})
    candidates = []
    for i in range(start, end):
        kind = _kind(units[i])
        if (kind not in priorities or not safe(i) or compact(units[i]) in answered
                or len(units[i]) > 180):
            continue
        score = priorities[kind] + sum(w in units[i] for w in ('상담', '보조제', '지원')) - abs(i-anchor) / 100
        candidates.append((score, i, kind))
    added = set()
    for _, i, kind in sorted(candidates, reverse=True):
        if kind in added:
            continue
        # Conflicting venue/time rows require a more precise request.
        if kind in ('location', 'hours') and len({compact(units[j]) for _, j, k in candidates if k == kind}) > 1:
            continue
        if append(i, usage=True):
            added.add(kind)
            if len(added) == 2:
                break
    return answer
