from __future__ import annotations

from pathlib import Path

from doc_chunk.media.models import DocumentAssetEntry, DocumentAssetsFile
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.images_manifest import ImagesManifest
from doc_chunk.models.tables_manifest import TablesManifest
from doc_chunk.workspace.layout import OutputWorkspace


def _char_range_for_ref(
    blocks: ContentBlocksFile,
    *,
    image_ref: str | None = None,
    table_ref: str | None = None,
) -> tuple[int | None, int | None, int | None]:
    for block in blocks.blocks:
        if image_ref and block.image_ref == image_ref:
            return block.block_index, block.char_start, block.char_end
        if table_ref and block.table_ref == table_ref:
            return block.block_index, block.char_start, block.char_end
    return None, None, None


def _sort_key(entry: DocumentAssetEntry) -> tuple[int, str]:
    if entry.char_start is None:
        return (10**9, entry.ref)
    return (entry.char_start, entry.ref)


def collect_document_assets(workspace: OutputWorkspace | Path) -> DocumentAssetsFile:
    ws = workspace if isinstance(workspace, OutputWorkspace) else OutputWorkspace.open_existing(Path(workspace))
    blocks_file: ContentBlocksFile | None = None
    if ws.content_blocks_path.is_file():
        blocks_file = ContentBlocksFile.model_validate_json(
            ws.content_blocks_path.read_text(encoding="utf-8")
        )

    images: list[DocumentAssetEntry] = []
    if ws.images_manifest_path.is_file():
        manifest = ImagesManifest.model_validate_json(ws.images_manifest_path.read_text(encoding="utf-8"))
        for item in manifest.images:
            block_index, char_start, char_end = (None, None, None)
            if blocks_file is not None:
                block_index, char_start, char_end = _char_range_for_ref(
                    blocks_file, image_ref=item.image_ref
                )
            images.append(
                DocumentAssetEntry(
                    asset_type="image",
                    ref=item.image_ref,
                    source_block_index=block_index if block_index is not None else item.source_block_index,
                    char_start=char_start,
                    char_end=char_end,
                    preview=item.file_name,
                    meta={
                        "content_type": item.content_type,
                        "byte_size": item.byte_size,
                        "width": item.width,
                        "height": item.height,
                    },
                )
            )

    tables: list[DocumentAssetEntry] = []
    if ws.tables_manifest_path.is_file():
        manifest = TablesManifest.model_validate_json(ws.tables_manifest_path.read_text(encoding="utf-8"))
        for item in manifest.tables:
            block_index, char_start, char_end = (None, None, None)
            if blocks_file is not None:
                block_index, char_start, char_end = _char_range_for_ref(
                    blocks_file, table_ref=item.table_ref
                )
            tables.append(
                DocumentAssetEntry(
                    asset_type="table",
                    ref=item.table_ref,
                    source_block_index=block_index if block_index is not None else item.source_block_index,
                    char_start=char_start if char_start is not None else item.char_start,
                    char_end=char_end if char_end is not None else item.char_end,
                    preview=item.markdown_preview,
                    meta={
                        "layout_type": item.layout_type,
                        "row_count": item.row_count,
                        "col_count": item.col_count,
                    },
                )
            )

    return DocumentAssetsFile(
        images=sorted(images, key=_sort_key),
        tables=sorted(tables, key=_sort_key),
    )
