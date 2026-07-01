from __future__ import annotations

from pathlib import Path

from doc_chunk.extract.block_index import BlockAccumulator, write_content_blocks
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.table.placeholders import format_table_ref_comment
from doc_chunk.workspace.layout import OutputWorkspace


def test_block_accumulator_tracks_char_offsets(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    acc = BlockAccumulator()
    acc.add_paragraph("第一章 总则")
    acc.add_paragraph("正文段落。")
    acc.add_table("| a | b |\n| --- | --- |\n| 1 | 2 |")
    acc.add_image("images/docx-img-001.png")

    blocks_file = acc.finalize()
    assert len(blocks_file.blocks) == 4
    assert blocks_file.blocks[0].block_type == "paragraph"
    assert blocks_file.blocks[0].char_start == 0
    assert blocks_file.blocks[1].char_start >= blocks_file.blocks[0].char_end
    assert blocks_file.blocks[2].block_type == "table"
    assert blocks_file.blocks[3].block_type == "image"

    path = write_content_blocks(ws, blocks_file)
    loaded = ContentBlocksFile.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded.schema_version == "1.1"
    assert len(loaded.blocks) == 4


def test_block_accumulator_table_ref() -> None:
    acc = BlockAccumulator()
    acc.add_table("| a | b |", table_ref="tables/t0000.json")
    blocks_file = acc.finalize()
    assert blocks_file.schema_version == "1.1"
    assert blocks_file.blocks[0].table_ref == "tables/t0000.json"


def test_block_accumulator_table_writes_placeholder_in_markdown() -> None:
    acc = BlockAccumulator()
    acc.add_table("| a | b |", table_ref="tables/t0000.json")
    md = acc.markdown
    assert format_table_ref_comment("tables/t0000.json") in md
    assert "| a | b |" in md
    block = acc.finalize().blocks[0]
    assert block.char_start == 0
    assert md[block.char_start : block.char_end].startswith("<!-- table-ref:")


def test_extract_writes_images_manifest(sample_docx_with_image: Path, tmp_path: Path) -> None:
    from doc_chunk.extract.docx_extractor import extract_docx
    from doc_chunk.models.images_manifest import ImagesManifest

    ws = OutputWorkspace.create(tmp_path / "ws-img", overwrite=True)
    extract_docx(sample_docx_with_image, ws)
    manifest_path = ws.images_manifest_path
    assert manifest_path.exists()
    data = ImagesManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    assert len(data.images) == 1
    assert data.images[0].image_ref.startswith("images/")
    assert data.images[0].content_type.startswith("image/")
    assert data.images[0].source_block_index is not None
