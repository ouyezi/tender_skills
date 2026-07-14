from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": _WORD_NS}
_TOC_NAME_RE = re.compile(r"^toc\s*(\d+)\s*$", re.IGNORECASE)
_TOC_STYLE_RE = re.compile(r"^toc(\d+)$", re.IGNORECASE)


def build_toc_style_level_map(styles_xml: bytes) -> dict[str, int]:
    try:
        root = etree.fromstring(styles_xml)
    except Exception:
        return {}
    mapping: dict[str, int] = {}
    for style in root.xpath(".//w:style[@w:type='paragraph']", namespaces=_NS):
        style_id = style.get(f"{{{_WORD_NS}}}styleId")
        if not style_id:
            continue
        name = style.xpath("string(./w:name/@w:val)", namespaces=_NS).strip()
        match = _TOC_NAME_RE.match(name)
        if not match:
            continue
        mapping[style_id] = max(1, min(8, int(match.group(1))))
    return mapping


def resolve_toc_level(style_val: str, toc_style_map: dict[str, int]) -> int | None:
    if not style_val:
        return None
    if style_val in toc_style_map:
        return toc_style_map[style_val]
    match = _TOC_STYLE_RE.match(style_val.strip())
    if match:
        return max(1, min(8, int(match.group(1))))
    return None


def load_toc_style_map_from_docx(path: Path) -> dict[str, int]:
    try:
        with ZipFile(path, "r") as archive:
            try:
                styles_xml = archive.read("word/styles.xml")
            except KeyError:
                return {}
    except Exception:
        return {}
    return build_toc_style_level_map(styles_xml)
