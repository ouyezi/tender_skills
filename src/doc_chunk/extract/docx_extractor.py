from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph

from typing import Literal

from doc_chunk.extract.block_index import BlockAccumulator, write_accumulator_markdown, write_content_blocks
from doc_chunk.extract.docx_numbering import DocxNumberingResolver, merge_list_prefix
from doc_chunk.extract.promote_headings import parse_content_heading_line
from doc_chunk.models.document import ExtractResult
from doc_chunk.models.images_manifest import ImageManifestEntry, ImagesManifest
from doc_chunk.workspace.layout import OutputWorkspace


def _heading_level_from_style(style_name: str) -> int | None:
    name = style_name.strip()
    parts = name.split()
    if len(parts) == 2 and parts[1].isdigit():
        if parts[0] in {"Heading", "标题"}:
            return max(1, min(8, int(parts[1])))
    return None


def _outline_level_from_paragraph(paragraph: DocxParagraph) -> int | None:
    p_pr = paragraph._element.pPr
    if p_pr is None:
        return None
    outline_lvl = p_pr.find(qn("w:outlineLvl"))
    if outline_lvl is None:
        return None
    raw = outline_lvl.get(qn("w:val"))
    if raw is None:
        return None
    try:
        level = int(raw) + 1
    except ValueError:
        return None
    if not 1 <= level <= 8:
        return None
    return level


def _resolve_paragraph_heading_level(paragraph: DocxParagraph, text: str) -> int | None:
    level = _heading_level_from_style(paragraph.style.name)
    if level is not None:
        return level

    outline_level = _outline_level_from_paragraph(paragraph)
    if outline_level is not None and parse_content_heading_line(text) is not None:
        return outline_level

    return None


def _docx_element_image_parts(element: object, doc: DocxDocument) -> list[object]:
    image_parts: list[object] = []
    for child in element.iter():
        if child.tag != qn("a:blip"):
            continue
        relationship_id = child.get(qn("r:embed"))
        if relationship_id is None:
            continue
        image_part = doc.part.related_parts.get(relationship_id)
        if image_part is not None:
            image_parts.append(image_part)
    return image_parts


def _docx_paragraph_image_parts(paragraph: DocxParagraph, doc: DocxDocument) -> list[object]:
    return _docx_element_image_parts(paragraph._element, doc)


def _docx_table_image_parts(table: DocxTable, doc: DocxDocument) -> list[object]:
    image_parts: list[object] = []
    seen_cells: set[int] = set()
    for row in table.rows:
        for cell in row.cells:
            cell_id = id(cell._tc)
            if cell_id in seen_cells:
                continue
            seen_cells.add(cell_id)
            for paragraph in cell.paragraphs:
                image_parts.extend(_docx_paragraph_image_parts(paragraph, doc))
    return image_parts


def _image_extension(partname: object, content_type: str) -> str:
    suffix = Path(str(partname)).suffix.lower()
    if suffix:
        return suffix
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type.lower(), ".bin")


def _save_docx_image(workspace: OutputWorkspace, image_part: object, image_number: int) -> str:
    extension = _image_extension(image_part.partname, image_part.content_type)
    image_name = f"docx-img-{image_number:03d}{extension}"
    (workspace.images_dir / image_name).write_bytes(image_part.blob)
    return image_name


def _table_to_markdown(table: DocxTable) -> str:
    rows = [[cell.text.strip().replace("\n", " ") for cell in row.cells] for row in table.rows]
    if not rows:
        return ""
    column_count = max(len(row) for row in rows)
    if column_count == 0:
        return ""
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    header = normalized_rows[0]
    lines = [
        f"| {' | '.join(header)} |",
        f"| {' | '.join('---' for _ in range(column_count))} |",
    ]
    lines.extend(f"| {' | '.join(row)} |" for row in normalized_rows[1:])
    return "\n".join(lines)


def extract_docx(
    path: Path,
    workspace: OutputWorkspace,
    *,
    promote_headings: Literal["off", "auto"] = "off",
) -> ExtractResult:
    doc = DocxDocument(path)
    numbering = DocxNumberingResolver(doc)
    acc = BlockAccumulator()
    image_count = 0
    image_entries: list[ImageManifestEntry] = []

    for element in doc.element.body.iterchildren():
        if element.tag.endswith("}p"):
            paragraph = DocxParagraph(element, doc)
            list_prefix = numbering.advance(paragraph)
            text = paragraph.text.strip()
            if text and list_prefix:
                text = merge_list_prefix(text, list_prefix)
            if text:
                level = _resolve_paragraph_heading_level(paragraph, text)
                if level is not None:
                    acc.add_heading(level, text)
                elif promote_headings == "auto":
                    parsed = parse_content_heading_line(text)
                    if parsed is not None:
                        acc.add_heading(parsed[0], parsed[1])
                    else:
                        acc.add_paragraph(text)
                else:
                    acc.add_paragraph(text)
            for image_part in _docx_paragraph_image_parts(paragraph, doc):
                image_count += 1
                image_name = _save_docx_image(workspace, image_part, image_count)
                image_ref = f"images/{image_name}"
                block_index_before = acc.block_count
                acc.add_image(image_ref, alt=f"docx-img-{image_count:03d}")
                image_entries.append(
                    ImageManifestEntry(
                        image_ref=image_ref,
                        file_name=image_name,
                        content_type=image_part.content_type,
                        byte_size=len(image_part.blob),
                        source_block_index=block_index_before,
                    )
                )
            continue

        if element.tag.endswith("}tbl"):
            table = DocxTable(element, doc)
            table_md = _table_to_markdown(table)
            if table_md:
                acc.add_table(table_md)
            for image_part in _docx_table_image_parts(table, doc):
                image_count += 1
                image_name = _save_docx_image(workspace, image_part, image_count)
                image_ref = f"images/{image_name}"
                block_index_before = acc.block_count
                acc.add_image(image_ref, alt=f"docx-img-{image_count:03d}")
                image_entries.append(
                    ImageManifestEntry(
                        image_ref=image_ref,
                        file_name=image_name,
                        content_type=image_part.content_type,
                        byte_size=len(image_part.blob),
                        source_block_index=block_index_before,
                    )
                )

    write_accumulator_markdown(workspace, acc)
    write_content_blocks(workspace, acc.finalize())
    if image_entries:
        manifest = ImagesManifest(images=image_entries)
        workspace.images_manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return ExtractResult(image_count=image_count, warnings=[])
