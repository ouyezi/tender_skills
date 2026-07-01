from __future__ import annotations

import re

_CN_CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百千0-9]+[章节编部分卷篇]\s+(.+)$")
_CN_ENUM_RE = re.compile(r"^[一二三四五六七八九十百零]+、\s*\S")
_NUM_HEADING_RE = re.compile(r"^(\d+(?:\.\d+){0,7})[\s、.．]+(.+)$")


def parse_content_heading_line(line: str) -> tuple[int, str] | None:
    """Detect numbered / 第X章 / X、 style headings in plain text (no Word Heading style)."""
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return None
    cn_match = _CN_CHAPTER_RE.match(stripped)
    if cn_match:
        title = cn_match.group(1).strip() or stripped
        return 1, title
    if _CN_ENUM_RE.match(stripped):
        return 1, stripped
    numeric = _NUM_HEADING_RE.match(stripped)
    if numeric:
        seq = numeric.group(1)
        title = numeric.group(2).strip()
        if title:
            level = min(seq.count(".") + 1, 8)
            return level, title
    return None
