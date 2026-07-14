from __future__ import annotations

import re

_CN_CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百千0-9]+[章节编部分卷篇]\s+(.+)$")
_CN_ENUM_RE = re.compile(r"^([一二三四五六七八九十百零]+)、(.+)$")
_CN_LIST_ITEM_RE = re.compile(r"^\d+[、]")
_NUM_HEADING_RE = re.compile(
    r"^(\d+(?:\.\d+)+)([^\d].+)$|"
    r"^(\d+)\.[ \t]+(.+)$|"
    r"^(\d+)[ \t]+(.+)$"
)
_CN_ENUM_MAX_LEN = 60
_COLON_LIST_BODY_RE = re.compile(r"^[^：:\n]{2,40}[：:].+")
_CN_LOCAL_ENUM_PARA_RE = re.compile(r"^[一二三四五六七八九十]+、.+[：:]\s*$")
_CN_ENUM_PREFIX_RE = re.compile(r"^[一二三四五六七八九十百零]+、[ \t]*")
_DECIMAL_SECTION_RE = re.compile(r"^\d+(?:\.\d+)+")
_TOC_PAGE_SUFFIX_RE = re.compile(r"[\t]\d+\s*$")
_GLUED_PAGE_RE = re.compile(r"^(?P<title>.+?\D)(?P<page>\d{1,3})$")
_DOTTED_LEADER_RE = re.compile(
    r"^.+?[.\u2026\u3002]{2,}\s*-?\s*\d+\s*-?\s*$"
)
_TOC_LINE_MAX_LEN = 120
_CN_OR_SECTION_RE = re.compile(r"[\u4e00-\u9fff]|(?:^[一二三四五六七八九十百零]+、)|(?:^\d+(?:\.\d+)*[.\s、])")


def is_toc_entry_line(line: str) -> bool:
    """TOC row: tab+page, glued page, or dotted leaders + page (must not become a section heading)."""
    stripped = line.strip()
    if not stripped or len(stripped) > _TOC_LINE_MAX_LEN:
        return False
    if _TOC_PAGE_SUFFIX_RE.search(stripped):
        return True
    if _DOTTED_LEADER_RE.match(stripped):
        return True
    glued = _GLUED_PAGE_RE.match(stripped)
    if glued is None:
        return False
    title = glued.group("title").strip()
    return bool(title) and _CN_OR_SECTION_RE.search(title) is not None


def is_decimal_section_title(title: str) -> bool:
    """True for multi-level numeric titles like「7.2丰富的商品资源」."""
    return bool(_DECIMAL_SECTION_RE.match(title.strip()))


class PromoteHeadingsState:
    """Track local 一、…： / 二、…： lists so continuations are not promoted to headings."""

    def __init__(self) -> None:
        self.in_local_cn_enum_series = False
        # After「7.2…」etc., a following「一、…」is usually a local list item, not a new L1.
        self.after_decimal_section = False

    def note_heading(self, level: int, title: str) -> None:
        """Update state when a heading is emitted (Word style or promote)."""
        stripped = title.strip()
        if is_decimal_section_title(stripped):
            self.after_decimal_section = True
            return
        if level <= 1 and is_cn_enum_chapter_line(stripped):
            self.in_local_cn_enum_series = False
            self.after_decimal_section = False

    def parse(self, line: str) -> tuple[int, str] | None:
        stripped = line.strip()
        if is_cn_local_enum_paragraph(stripped):
            self.in_local_cn_enum_series = True
            self.after_decimal_section = False
            return None
        if self.in_local_cn_enum_series and is_cn_enum_chapter_line(stripped):
            return None
        cn_enum = _CN_ENUM_RE.match(stripped)
        if self.after_decimal_section and cn_enum is not None:
            # 「一、」right after 7.2-style heading → local list;「二、/三、」without a prior
            # local「一、」still count as real L1 chapters (see cn_enum promote tests).
            if cn_enum.group(1) == "一":
                self.in_local_cn_enum_series = True
                self.after_decimal_section = False
                return None
            self.after_decimal_section = False
        parsed = parse_content_heading_line(stripped)
        if parsed is None:
            return None
        level, title = parsed
        self.note_heading(level, title)
        return parsed


def is_cn_local_enum_paragraph(line: str) -> bool:
    """Paragraph like「一、员工投诉反馈机制：」— starts a local 一、二、三、 list."""
    return bool(_CN_LOCAL_ENUM_PARA_RE.match(line.strip()))


def is_cn_enum_chapter_line(line: str) -> bool:
    return bool(_CN_ENUM_RE.match(line.strip()))


def is_list_body_line(line: str) -> bool:
    """Plain-text list/bullet lines that must not become section headings."""
    stripped = line.strip()
    if not stripped:
        return False
    if _CN_LIST_ITEM_RE.match(stripped):
        return True
    if _COLON_LIST_BODY_RE.match(stripped) and not _CN_ENUM_RE.match(stripped):
        return True
    return False


def parse_content_heading_line(line: str) -> tuple[int, str] | None:
    """Detect numbered / 第X章 / X、 style headings in plain text (no Word Heading style)."""
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return None
    if is_toc_entry_line(stripped):
        return None
    if is_list_body_line(stripped):
        return None
    cn_match = _CN_CHAPTER_RE.match(stripped)
    if cn_match:
        return 1, stripped
    cn_enum = _CN_ENUM_RE.match(stripped)
    if cn_enum:
        body = cn_enum.group(2).strip()
        if not body or body.endswith(("：", ":")):
            return None
        if len(stripped) > _CN_ENUM_MAX_LEN:
            return None
        return 1, stripped
    numeric = _NUM_HEADING_RE.match(stripped)
    if numeric:
        if numeric.group(1):
            seq = numeric.group(1)
            title = numeric.group(2).strip()
        elif numeric.group(3):
            seq = numeric.group(3)
            title = numeric.group(4).strip()
        else:
            seq = numeric.group(5)
            title = numeric.group(6).strip()
        if not title or title.endswith(("：", ":")):
            return None
        level = min(seq.count(".") + 1, 8)
        if level == 1 and (len(title) > 50 or "：" in title or ":" in title):
            return None
        return level, stripped
    return None
