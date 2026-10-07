"""Recognize complete answer units without inventing a missing ending."""
from __future__ import annotations

import re

OMISSION = "[…]"
QUALIFICATION = re.compile(r"^(?:단[,， ]|다만|※|예외|제외|주의)")
_ENDING = re.compile(r"(?:니다|세요|시오|해요|돼요|어요|아요|인가요|일까요|할까요|습니까|바랍니다|바람)[.!?。！？]?$|다[.。]$|[!?？]$")
_DANGLING = re.compile(r"(?:[,，:：/·]|(?:하여|하며|이며|으며|하고|되고|하거나|따라|위해|통해|경우|때|대한|위한|있는|없는|하는|되는|한해|한|할|된|될|인|은|는|이|가|을|를|의|에서|에게|로|와|과))$")


def balanced(text: str) -> bool:
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
    noun_list = bool(re.search(r"(?:가능|불가|금지|제출|접수|방문상담|신청|예약|지참|제외|포함|부과|배출|운영|지원|문의|필요|이내|이상|미만)$", plain))
    return label_value or noun_list


def can_continue(text: str) -> bool:
    """Only join wrapped prose/parentheses, not unrelated table cells."""
    if OMISSION in text or sentence_complete(text):
        return False
    plain = text.strip().replace('**', '')
    return (not balanced(text) or bool(_DANGLING.search(plain))) and len(plain) >= 6


def complete_source_units(lines: list[str]) -> list[str]:
    units: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith((':', '：')) and units and len(units[-1]) < 20:
            units[-1] += ' ' + line
        elif (units and can_continue(units[-1]) and line != OMISSION
              and not QUALIFICATION.match(line)
              and not re.match(r"^(?:[-•❖]|\d+[.)]|[^:：]{1,30}[:：])", line)
              and (len(line) >= 12 or sentence_complete(line) or not balanced(units[-1]))):
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
