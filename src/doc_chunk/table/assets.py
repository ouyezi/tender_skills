from __future__ import annotations

from pathlib import Path

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.tables_manifest import TableManifestEntry, TablesManifest
from doc_chunk.table.access import load_table_model
from doc_chunk.workspace.layout import OutputWorkspace


def collect_table_assets(
    workspace: OutputWorkspace | Path,
    *,
    write_manifest: bool = True,
) -> TablesManifest:
    ws = workspace if isinstance(workspace, OutputWorkspace) else OutputWorkspace.open_existing(Path(workspace))
    blocks_path = ws.content_blocks_path
    if not blocks_path.is_file():
        return TablesManifest()

    blocks_file = ContentBlocksFile.model_validate_json(blocks_path.read_text(encoding="utf-8"))
    entries: list[TableManifestEntry] = []

    for block in blocks_file.blocks:
        if block.block_type != "table" or not block.table_ref:
            continue
        sidecar = load_table_model(ws, block.table_ref)
        row_count = len(sidecar.logical_rows) or len(sidecar.grid.get("rows", []))
        col_count = sidecar.grid_width
        slice_ref = sidecar.slice_ref
        slice_status = sidecar.slice_status
        slice_byte_size = None
        if slice_ref and (ws.root / slice_ref).is_file():
            slice_byte_size = (ws.root / slice_ref).stat().st_size
        entries.append(
            TableManifestEntry(
                table_ref=block.table_ref,
                slice_ref=slice_ref,
                slice_status=slice_status,
                slice_byte_size=slice_byte_size,
                source_block_index=block.block_index,
                layout_type=sidecar.layout_type,
                row_count=row_count,
                col_count=col_count,
                char_start=block.char_start,
                char_end=block.char_end,
                markdown_preview=block.text_preview,
            )
        )

    manifest = TablesManifest(schema_version="1.1", tables=sorted(entries, key=lambda e: e.source_block_index))
    if write_manifest:
        ws.tables_dir.mkdir(parents=True, exist_ok=True)
        ws.tables_manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest
