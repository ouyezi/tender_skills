from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

_DOC_XML_PATH = "word/document.xml"
_STYLES_XML_PATH = "word/styles.xml"
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": _WORD_NS}
_TRAILING_PAGE_RE = re.compile(r"\s+\d+\s*$")
_GLUED_PAGE_RE = re.compile(r"^(?P<title>.+?\D)(?P<page>\d{1,3})$")
_TOC_STYLE_RE = re.compile(r"^toc(\d+)$")
_TOC_NAME_RE = re.compile(r"^toc\s*(\d+)\s*$", re.IGNORECASE)


def _join_toc_text_parts(parts: list[str]) -> str:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    if not cleaned:
        return ""
    if len(cleaned) >= 2 and cleaned[-1].isdigit():
        return "".join(cleaned[:-1])
    joined = "".join(cleaned)
    glued = _GLUED_PAGE_RE.match(joined)
    if glued is not None:
        return glued.group("title")
    return _TRAILING_PAGE_RE.sub("", joined).strip()


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
        level = max(1, min(8, int(match.group(1))))
        mapping[style_id] = level
    return mapping


def _resolve_toc_level(style_val: str, toc_style_map: dict[str, int]) -> int | None:
    if not style_val:
        return None
    if style_val in toc_style_map:
        return toc_style_map[style_val]
    match = _TOC_STYLE_RE.match(style_val.strip().lower())
    if match:
        return max(1, min(8, int(match.group(1))))
    return None


def extract_docx_toc_outline(source_path: Path) -> OutlineTree | None:
    try:
        with ZipFile(source_path, "r") as archive:
            document_xml = archive.read(_DOC_XML_PATH)
            try:
                styles_xml = archive.read(_STYLES_XML_PATH)
            except KeyError:
                styles_xml = b""
    except Exception:
        return None

    try:
        root = etree.fromstring(document_xml)
    except Exception:
        return None

    has_toc_field = any(
        "TOC" in ("".join(instr.itertext()) if instr is not None else "").upper()
        for instr in root.xpath(".//w:instrText", namespaces=_NS)
    )
    if not has_toc_field:
        return None

    toc_style_map = build_toc_style_level_map(styles_xml)

    nodes: list[OutlineNode] = []
    last_seen_by_level: dict[int, str] = {}
    sort_order = 0

    for paragraph in root.xpath(".//w:p", namespaces=_NS):
        style_val = paragraph.xpath("string(./w:pPr/w:pStyle/@w:val)", namespaces=_NS).strip()
        level = _resolve_toc_level(style_val, toc_style_map)
        if level is None:
            continue

        text_parts = paragraph.xpath(".//w:t/text()", namespaces=_NS)
        title = _join_toc_text_parts(text_parts)
        if not title:
            continue

        parent_id = None
        if level > 1:
            for parent_level in range(level - 1, 0, -1):
                parent_id = last_seen_by_level.get(parent_level)
                if parent_id:
                    break

        node_id = f"n{len(nodes) + 1}"
        nodes.append(
            OutlineNode(
                node_id=node_id,
                title=title,
                level=level,
                parent_id=parent_id,
                sort_order=sort_order,
                anchor=Anchor(block_index=sort_order),
            )
        )
        sort_order += 1
        last_seen_by_level[level] = node_id
        for stale_level in list(last_seen_by_level):
            if stale_level > level:
                last_seen_by_level.pop(stale_level, None)

    if not nodes:
        return None
    return OutlineTree(strategy="toc", nodes=nodes)
