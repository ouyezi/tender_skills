from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,8})[ \t]+(.+?)[ \t#]*$", re.MULTILINE)


def slice_by_heading_level(content_md: str, start: int, level: int) -> tuple[str, int]:
    end = len(content_md)
    for match in _HEADING_RE.finditer(content_md):
        if match.start() <= start:
            continue
        if len(match.group(1)) <= level:
            end = match.start()
            break
    return content_md[start:end].strip(), end
