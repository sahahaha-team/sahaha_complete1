"""Read mandatory groups explicitly declared by the source, without values."""
import re
from chatbot.answer_completion import source_unit_complete


def applicant_qualification_supported(query: str, units: list[str]) -> bool:
    """A household-count note cannot establish the applicant's nationality."""
    if '외국인' not in re.sub(r'\s+', '', query):
        return True
    for unit in units:
        if not source_unit_complete(unit) or '외국인' not in unit:
            continue
        if re.search(r'가구원|가구\s*수|소득\s*조사|소득\s*산정', unit):
            continue
        if re.search(r'대상|자격|신청|지원|이용|참여|가능|제외|불가', unit):
            return True
    return False


def mandatory_criteria_groups(units: list[str]) -> list[tuple[int,list[int]]]:
    groups=[]
    for index,unit in enumerate(units):
        count=re.search(r'(?:아래|다음)\s*(\d+)\s*(?:가지)?\s*(?:조건|요건|기준)',unit)
        if not count or '모두' not in unit:
            continue
        expected=int(count[1])
        if not 1 <= expected <= 10:
            continue
        criteria=[]
        for pos in range(index+1,len(units)):
            following=units[pos].removeprefix('- ').strip()
            if following.startswith(('#','[')):
                break
            if re.match(r'[^:：]{1,16}기준\s*[:：]',following):
                if not source_unit_complete(following):
                    criteria=[];break
                criteria.append(pos)
            elif criteria:
                break
        if len(criteria)==expected:
            groups.append((index,criteria))
    return groups
