from __future__ import annotations

from pathlib import Path

from doc_chunk.extract.block_index import BlockAccumulator, write_accumulator_markdown, write_content_blocks
from doc_chunk.models.table_model import TableSidecar
from doc_chunk.models.tables_manifest import TablesManifest
from doc_chunk.table.assets import collect_table_assets
from doc_chunk.workspace.layout import OutputWorkspace


def _write_minimal_sidecar(ws: OutputWorkspace, block_index: int = 0) -> str:
    ref = f"tables/t{block_index:04d}.json"
    sidecar = TableSidecar(
        block_index=block_index,
        layout_type="simple",
        grid_width=2,
        grid={"rows": [{"cells": [{"text": "a", "colspan": 1, "rowspan": 1}]}]},
        logical_rows=[["a", "b"]],
        markdown="| a | b |",
        llm_text="table",
    )
    path = ws.root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sidecar.model_dump_json(indent=2), encoding="utf-8")
    return ref


def test_collect_table_assets_builds_manifest(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    ref = _write_minimal_sidecar(ws)
    acc = BlockAccumulator()
    acc.add_table("| a | b |", table_ref=ref)
    write_accumulator_markdown(ws, acc)
    write_content_blocks(ws, acc.finalize())

    manifest = collect_table_assets(ws, write_manifest=True)
    assert len(manifest.tables) == 1
    assert manifest.tables[0].table_ref == ref
    assert manifest.tables[0].layout_type == "simple"
    assert ws.tables_manifest_path.exists()
    loaded = TablesManifest.model_validate_json(ws.tables_manifest_path.read_text(encoding="utf-8"))
    assert loaded.tables[0].source_block_index == 0


def test_collect_table_assets_includes_slice_metadata(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws-slice", overwrite=True)
    ref = "tables/t0000.json"
    slice_ref = "tables/t0000.docx"
    sidecar = TableSidecar(
        schema_version="1.1",
        block_index=0,
        slice_ref=slice_ref,
        slice_status="ok",
        layout_type="simple",
        grid_width=2,
        grid={"rows": []},
        logical_rows=[["a", "b"]],
        markdown="| a | b |",
        llm_text="table",
    )
    (ws.root / ref).write_text(sidecar.model_dump_json(indent=2), encoding="utf-8")
    (ws.root / slice_ref).write_bytes(b"PK" + b"x" * 100)

    acc = BlockAccumulator()
    acc.add_table("| a | b |", table_ref=ref)
    write_accumulator_markdown(ws, acc)
    write_content_blocks(ws, acc.finalize())

    manifest = collect_table_assets(ws, write_manifest=True)
    entry = manifest.tables[0]
    assert manifest.schema_version == "1.1"
    assert entry.slice_ref == slice_ref
    assert entry.slice_status == "ok"
    assert entry.slice_byte_size == 102
