from __future__ import annotations

from pathlib import Path

from doc_chunk.extract.block_index import BlockAccumulator, write_accumulator_markdown, write_content_blocks
from doc_chunk.media.assets import collect_document_assets
from doc_chunk.models.images_manifest import ImageManifestEntry, ImagesManifest
from doc_chunk.models.table_model import TableSidecar
from doc_chunk.models.tables_manifest import TableManifestEntry, TablesManifest
from doc_chunk.workspace.layout import OutputWorkspace


def _write_table_sidecar(ws: OutputWorkspace, ref: str = "tables/t0000.json") -> None:
    sidecar = TableSidecar(
        block_index=0,
        layout_type="simple",
        grid_width=2,
        grid={"rows": [{"cells": [{"text": "a", "colspan": 1, "rowspan": 1}]}]},
        logical_rows=[["a", "b"]],
        markdown="| a | b |",
        llm_text="table",
    )
    (ws.root / ref).parent.mkdir(parents=True, exist_ok=True)
    (ws.root / ref).write_text(sidecar.model_dump_json(indent=2), encoding="utf-8")


def test_collect_document_assets_merges_images_and_tables(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    _write_table_sidecar(ws)
    acc = BlockAccumulator()
    acc.add_table("| a | b |", table_ref="tables/t0000.json")
    acc.add_image("images/img.png", alt="img")
    write_accumulator_markdown(ws, acc)
    write_content_blocks(ws, acc.finalize())

    (ws.images_dir / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    images_manifest = ImagesManifest(
        images=[
            ImageManifestEntry(
                image_ref="images/img.png",
                file_name="img.png",
                content_type="image/png",
                source_block_index=1,
            )
        ]
    )
    ws.images_manifest_path.write_text(images_manifest.model_dump_json(indent=2), encoding="utf-8")
    tables_manifest = TablesManifest(
        tables=[
            TableManifestEntry(
                table_ref="tables/t0000.json",
                source_block_index=0,
                layout_type="simple",
                row_count=1,
                col_count=2,
                char_start=0,
                char_end=50,
                markdown_preview="| a | b |",
            )
        ]
    )
    ws.tables_manifest_path.write_text(tables_manifest.model_dump_json(indent=2), encoding="utf-8")

    doc = collect_document_assets(ws)
    assert len(doc.tables) == 1
    assert doc.tables[0].ref == "tables/t0000.json"
    assert doc.tables[0].char_start is not None
    assert len(doc.images) == 1
    assert doc.images[0].ref == "images/img.png"
    assert doc.images[0].preview == "img.png"
    assert doc.images[0].meta.get("content_type") == "image/png"
