from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from doc_chunk.locate.heading_starts import infer_body_start, normalize_outline_title
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.outline import OutlineTree

_DOC_XML_PATH = "word/document.xml"
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": _WORD_NS}
_TOC_BOOKMARK_PREFIX = "toc_bookmark:"


def _paragraph_text(paragraph: etree._Element) -> str:
    parts = paragraph.xpath(".//w:t/text()", namespaces=_NS)
    return "".join(parts).strip()


def _build_bookmark_target_map(document_xml: bytes) -> dict[str, str]:
    try:
        root = etree.fromstring(document_xml)
    except Exception:
        return {}

    paragraphs = root.xpath(".//w:p", namespaces=_NS)
    mapping: dict[str, str] = {}

    for idx, paragraph in enumerate(paragraphs):
        for bookmark in paragraph.xpath(".//w:bookmarkStart", namespaces=_NS):
            name = bookmark.get(f"{{{_WORD_NS}}}name")
            if not name:
                continue
            text = _paragraph_text(paragraph)
            if not text:
                for follow in paragraphs[idx + 1 :]:
                    text = _paragraph_text(follow)
                    if text:
                        break
            if text:
                mapping[name] = text
    return mapping


def _extract_toc_bookmark_ref(source_refs: list[str]) -> str | None:
    for ref in source_refs:
        if ref.startswith(_TOC_BOOKMARK_PREFIX):
            return ref[len(_TOC_BOOKMARK_PREFIX) :]
    return None


def _block_title_text(preview: str) -> str:
    stripped = preview.strip()
    if stripped.startswith("#"):
        return stripped.lstrip("#").strip()
    return stripped


def _find_body_block_for_title(
    title: str,
    blocks: ContentBlocksFile,
    content_md: str,
    *,
    body_start: int,
) -> int | None:
    target = normalize_outline_title(title)
    if not target:
        return None
    for block in blocks.blocks:
        if block.block_type not in {"heading", "paragraph"}:
            continue
        if block.char_start < body_start:
            continue
        preview = (block.text_preview or content_md[block.char_start : block.char_end]).strip()
        if normalize_outline_title(_block_title_text(preview)) == target:
            return block.block_index
    return None


def apply_toc_bookmark_anchors(
    tree: OutlineTree,
    source_path: Path,
    blocks: ContentBlocksFile,
    *,
    content_md: str,
) -> OutlineTree:
    """Fill anchor.block_index from toc_bookmark:* source_refs when resolvable."""
    try:
        with ZipFile(source_path, "r") as archive:
            document_xml = archive.read(_DOC_XML_PATH)
    except Exception:
        return tree

    bookmark_targets = _build_bookmark_target_map(document_xml)
    if not bookmark_targets:
        return tree

    body_start = infer_body_start(content_md)
    block_by_index = {b.block_index: b for b in blocks.blocks}
    new_nodes = []

    for node in tree.nodes:
        bookmark_name = _extract_toc_bookmark_ref(node.source_refs)
        if bookmark_name is None:
            new_nodes.append(node)
            continue

        target_title = bookmark_targets.get(bookmark_name)
        if target_title is None:
            new_nodes.append(node)
            continue

        block_index = _find_body_block_for_title(
            target_title, blocks, content_md, body_start=body_start
        )
        if block_index is None:
            new_nodes.append(node)
            continue

        block = block_by_index.get(block_index)
        if block is None:
            new_nodes.append(node)
            continue

        anchor = node.anchor.model_copy(
            update={
                "block_index": block_index,
                "block_start": block_index,
                "char_start": block.char_start,
                "char_end": block.char_end,
            }
        )
        new_nodes.append(node.model_copy(update={"anchor": anchor}))

    return tree.model_copy(update={"nodes": new_nodes})
