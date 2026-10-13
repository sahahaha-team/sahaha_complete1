"""Keep active source headings when a field omits its program's name."""
import re


def heading_path(units: list[str], index: int) -> str:
    stack = []
    for unit in units[:index + 1]:
        match = re.match(r'^(#{2,6})\s+(.+)',unit)
        if not match:
            continue
        level = len(match[1])
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level,match[2]))
    return ' > '.join(name for _level,name in stack)
