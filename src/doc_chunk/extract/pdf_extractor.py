from __future__ import annotations

from pathlib import Path

import fitz

from doc_chunk.extract.block_index import BlockAccumulator, write_accumulator_markdown, write_content_blocks
from doc_chunk.models.document import ExtractResult
from doc_chunk.workspace.layout import OutputWorkspace


def extract_pdf(path: Path, workspace: OutputWorkspace) -> ExtractResult:
    doc = fitz.open(path)
    acc = BlockAccumulator()
    warnings: list[str] = []
    image_count = 0

    try:
        for page_index, page in enumerate(doc, start=1):
            acc.add_heading(2, f"Page {page_index}")
            page_text = page.get_text("text").strip()
            if page_text:
                acc.add_paragraph(page_text)

            for image_index, image_info in enumerate(page.get_images(full=True), start=1):
                extracted = doc.extract_image(image_info[0])
                extension = str(extracted.get("ext") or "bin").lower().lstrip(".")
                image_name = f"page-{page_index:03d}-img-{image_index:03d}.{extension}"
                (workspace.images_dir / image_name).write_bytes(extracted["image"])
                image_count += 1
                acc.add_image(f"images/{image_name}", alt=f"page-{page_index:03d}-img-{image_index:03d}")

            if not page_text:
                warning = f"scanned_page_no_text: page {page_index}"
                warnings.append(warning)
                raster_name = f"page-{page_index:03d}.png"
                page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(
                    workspace.images_dir / raster_name
                )
                image_count += 1
                acc.add_image(f"images/{raster_name}", alt=f"page-{page_index:03d}")
    finally:
        doc.close()

    write_accumulator_markdown(workspace, acc)
    write_content_blocks(workspace, acc.finalize())
    return ExtractResult(image_count=image_count, warnings=warnings)
