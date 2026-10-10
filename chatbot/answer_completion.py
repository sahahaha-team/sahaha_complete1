"""Recognize complete answer units without inventing a missing ending."""
from __future__ import annotations

import re

OMISSION = "[…]"
QUALIFICATION = re.compile(r"^(?:단[,， ]|다만|※|예외|제외|주의)")
_ENDING = re.compile(r"(?:니다|세요|시오|해요|돼요|어요|아요|인가요|일까요|할까요|습니까|바랍니다|바람)[.!?。！？]?$|다[.。]$|[!?？]$")
_DANGLING = re.compile(r"(?:[,，:：/·]|[을를] 이용|(?:하여|하며|이며|으며|하고|되고|하거나|따라|위해|통해|경우|때|대한|위한|있는|없는|하는|되는|한해|한|할|된|될|인|은|는|이|가|을|를|의|에서|에게|로|와|과))$")


def balanced(text: str) -> bool:
    # Official Korean pages also write phone area codes as 051) 220-5716.
    # That closing parenthesis is phone notation, not unfinished prose.
    text = re.sub(r'(?<![\d(])(0\d{1,2})\)\s*(?=\d)', r'(\1)', text)
    stack = []
    pairs = {')': '(', ']': '[', '}': '{', '）': '（'}
    for char in text:
        if char in pairs.values():
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return False
    return not stack and text.count('**') % 2 == 0


def sentence_complete(text: str) -> bool:
    plain = text.strip().replace('**', '').rstrip('”’"\'')
    return balanced(text) and bool(_ENDING.search(plain))


def source_unit_complete(text: str) -> bool:
    """Allow factual label/value lists, but not unfinished Korean clauses."""
    if not text or OMISSION in text or not balanced(text):
        return False
    plain = text.strip().rstrip('.。').replace('**', '')
    if sentence_complete(text):
        return True
    if _DANGLING.search(plain):
        return False
    label_value = bool(re.match(r"[^:：]{1,30}[:：]\s*\S", plain))
    nominal = re.sub(r"\s*\([^()]*\)\s*$", "", plain)
    noun_list = bool(re.search(r"(?:가능|불가|금지|제출|접수|방문상담|신청|예약|지참|제외|포함|부과|배출|운영|지원|문의|필요|필수|이내|이상|미만|수거|처리|상담|발급|제공|기여|있음|없음|않음|됨|함)$", nominal))
    return label_value or noun_list


def can_continue(text: str) -> bool:
    """Only join wrapped prose/parentheses, not unrelated table cells."""
    if OMISSION in text or sentence_complete(text):
        return False
    plain = text.strip().replace('**', '')
    return (not balanced(text) or bool(_DANGLING.search(plain))) and len(plain) >= 6


def starts_label(text: str) -> bool:
    """The colon in 09:00 is a clock, not the start of a new source field."""
    match = re.match(r"^([^:：]{1,30})[:：]", text)
    return bool(match and not match.group(1).rstrip()[-1].isdigit())


def complete_source_units(lines: list[str]) -> list[str]:
    units: list[str] = []
    for index, line in enumerate(lines):
        line = re.sub(r"\.\s*\.$", ".", line.strip())
        if not line:
            continue
        if (units and not source_unit_complete(units[-1]) and len(line) < 80
                and index + 1 < len(lines)
                and re.match(r'^(?:[을를은는이가]|으로|로)\s', lines[index + 1].strip())):
            # HTML anchors often split a sentence into prefix / link name /
            # particle + ending. Rejoin adjacent text; no missing words are
            # generated, and headings/conditions keep their normal barriers.
            units[-1] += ' ' + line
        elif (units and not source_unit_complete(units[-1])
                and re.match(r'^(?:[을를은는이가]|으로|로)\s', line)):
            units[-1] += ' ' + line
        elif line.startswith((':', '：')) and units and len(units[-1]) < 20:
            units[-1] += ' ' + line
        elif (units and re.fullmatch(r"[^:：]{1,30}[:：]\s*", units[-1])
              and line != OMISSION and not QUALIFICATION.match(line) and not starts_label(line)):
            units[-1] += ' ' + line
        elif (units and can_continue(units[-1]) and line != OMISSION
              and not QUALIFICATION.match(line)
              and not re.match(r"^(?:[-•❖]|\d+[.)])", line) and not starts_label(line)
              and (len(line) >= 12 or source_unit_complete(line) or not balanced(units[-1])
                   or re.search(r"[을를] 이용$", line))):
            units[-1] += ' ' + line
        else:
            # Keep even incomplete units as barriers: they may be a condition
            # of the next sentence and must not silently disappear.
            units.append(line)
    return units


def model_answer_complete(text: str, metadata: dict | None = None, *, limit: int = 480) -> bool:
    """Do not salvage a token-limited reply by deleting its last condition."""
    if (metadata or {}).get('done_reason') in ('length', 'max_tokens'):
        return False
    if not text or len(text) > limit or OMISSION in text or not balanced(text):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return all(sentence_complete(line) for line in lines)
