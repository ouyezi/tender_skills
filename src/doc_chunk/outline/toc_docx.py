from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from doc_chunk.locate.heading_starts import ensure_section_prefix_spacing
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.outline.toc_styles import build_toc_style_level_map, resolve_toc_level

_DOC_XML_PATH = "word/document.xml"
_STYLES_XML_PATH = "word/styles.xml"
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": _WORD_NS}
_TRAILING_PAGE_RE = re.compile(r"\s+\d+\s*$")
_GLUED_PAGE_RE = re.compile(r"^(?P<title>.+?\D)(?P<page>\d{1,3})$")


def _join_toc_text_parts(parts: list[str]) -> str:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    if not cleaned:
        return ""
    if len(cleaned) >= 2 and cleaned[-1].isdigit():
        title = "".join(cleaned[:-1])
    else:
        joined = "".join(cleaned)
        glued = _GLUED_PAGE_RE.match(joined)
        if glued is not None:
            title = glued.group("title")
        else:
            title = _TRAILING_PAGE_RE.sub("", joined).strip()
    return ensure_section_prefix_spacing(title)


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
        level = resolve_toc_level(style_val, toc_style_map)
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
