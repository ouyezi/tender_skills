from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph as DocxParagraph

from doc_chunk.extract.promote_headings import parse_content_heading_line

_CN_LIST_PREFIX_RE = re.compile(r"^[一二三四五六七八九十百]+[、.．]")
_DECIMAL_LIST_PREFIX_RE = re.compile(r"^\d+[、.．]")


@dataclass(frozen=True)
class _LevelStyle:
    num_fmt: str
    lvl_text: str
    start: int


def _format_chinese_counting(value: int) -> str:
    if value <= 0:
        return str(value)
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    if value < 20:
        return "十" + (digits[value % 10] if value % 10 else "")
    if value < 100:
        tens, ones = divmod(value, 10)
        result = digits[tens] + "十"
        if ones:
            result += digits[ones]
        return result
    if value < 1000:
        hundreds, remainder = divmod(value, 100)
        result = digits[hundreds] + "百"
        if remainder:
            if remainder < 10:
                result += "零" + digits[remainder]
            else:
                result += _format_chinese_counting(remainder)
        return result
    return str(value)


def _format_number(value: int, num_fmt: str) -> str:
    if num_fmt in {"chineseCounting", "chineseCountingThousand", "ideographTraditional"}:
        return _format_chinese_counting(value)
    if num_fmt in {"chineseLegalSimplified", "chineseLegalTenThousand"}:
        legal = "零壹贰叁肆伍陆柒捌玖"
        if value <= 0:
            return str(value)
        if value < 10:
            return legal[value]
        return str(value)
    return str(value)


def _apply_lvl_text(template: str, values_by_level: dict[int, int], styles_by_level: dict[int, _LevelStyle]) -> str:
    result = template
    for level, value in sorted(values_by_level.items()):
        style = styles_by_level[level]
        formatted = _format_number(value, style.num_fmt)
        result = result.replace(f"%{level + 1}", formatted)
    return result


def merge_list_prefix(text: str, prefix: str) -> str:
    stripped = text.strip()
    if not stripped or not prefix:
        return stripped
    if _CN_LIST_PREFIX_RE.match(stripped) or _DECIMAL_LIST_PREFIX_RE.match(stripped):
        return stripped
    if parse_content_heading_line(stripped) is not None:
        return stripped
    if stripped.startswith(prefix):
        return stripped
    return f"{prefix}{stripped}"


class DocxNumberingResolver:
    def __init__(self, doc: DocxDocument) -> None:
        self._abstract_levels: dict[str, dict[int, _LevelStyle]] = {}
        self._num_to_abstract: dict[str, str] = {}
        self._counters: dict[str, dict[int, int]] = defaultdict(dict)
        self._load(doc)

    def advance(self, paragraph: DocxParagraph) -> str | None:
        p_pr = paragraph._element.pPr
        if p_pr is None:
            return None
        num_pr = p_pr.find(qn("w:numPr"))
        if num_pr is None:
            return None

        num_id_el = num_pr.find(qn("w:numId"))
        if num_id_el is None:
            return None
        num_id = num_id_el.get(qn("w:val"))
        if not num_id or num_id == "0":
            return None

        ilvl_el = num_pr.find(qn("w:ilvl"))
        ilvl = int(ilvl_el.get(qn("w:val"))) if ilvl_el is not None else 0

        abstract_id = self._num_to_abstract.get(num_id)
        if abstract_id is None:
            return None
        levels = self._abstract_levels.get(abstract_id)
        if levels is None or ilvl not in levels:
            return None

        counters = self._counters[num_id]
        style = levels[ilvl]
        if ilvl not in counters:
            counters[ilvl] = style.start
        else:
            counters[ilvl] += 1
        for deeper in list(counters):
            if deeper > ilvl:
                del counters[deeper]

        values_by_level: dict[int, int] = {}
        styles_by_level: dict[int, _LevelStyle] = {}
        for level in range(ilvl + 1):
            if level not in levels:
                continue
            level_style = levels[level]
            if level == ilvl:
                values_by_level[level] = counters[ilvl]
            else:
                values_by_level[level] = counters.get(level, level_style.start)
            styles_by_level[level] = level_style

        return _apply_lvl_text(style.lvl_text, values_by_level, styles_by_level)

    def _load(self, doc: DocxDocument) -> None:
        numbering_part = getattr(doc.part, "numbering_part", None)
        if numbering_part is None:
            return

        root = numbering_part.element
        for abstract in root.findall(qn("w:abstractNum")):
            abstract_id = abstract.get(qn("w:abstractNumId"))
            if abstract_id is None:
                continue
            levels: dict[int, _LevelStyle] = {}
            for lvl in abstract.findall(qn("w:lvl")):
                ilvl_raw = lvl.get(qn("w:ilvl"))
                if ilvl_raw is None:
                    continue
                ilvl = int(ilvl_raw)
                num_fmt_el = lvl.find(qn("w:numFmt"))
                lvl_text_el = lvl.find(qn("w:lvlText"))
                start_el = lvl.find(qn("w:start"))
                num_fmt = num_fmt_el.get(qn("w:val")) if num_fmt_el is not None else "decimal"
                lvl_text = lvl_text_el.get(qn("w:val")) if lvl_text_el is not None else f"%{ilvl + 1}."
                start = int(start_el.get(qn("w:val"))) if start_el is not None else 1
                levels[ilvl] = _LevelStyle(num_fmt=num_fmt, lvl_text=lvl_text, start=start)
            if levels:
                self._abstract_levels[abstract_id] = levels

        for num in root.findall(qn("w:num")):
            num_id = num.get(qn("w:numId"))
            abstract_id_el = num.find(qn("w:abstractNumId"))
            if num_id is None or abstract_id_el is None:
                continue
            abstract_id = abstract_id_el.get(qn("w:val"))
            if abstract_id is not None:
                self._num_to_abstract[num_id] = abstract_id
