from doc_chunk.models.content_block import ContentBlocksFile, ContentBlockRecord
from doc_chunk.models.table_model import TableCell, TableGridRow, TableSidecar, TablesIndex


def test_content_blocks_schema_1_1_accepts_table_ref() -> None:
    blocks = ContentBlocksFile(
        schema_version="1.1",
        blocks=[
            ContentBlockRecord(
                block_index=0,
                block_type="table",
                char_start=0,
                char_end=50,
                text_preview="| a | b |",
                table_ref="tables/t0000.json",
            )
        ],
    )
    assert blocks.schema_version == "1.1"
    assert blocks.blocks[0].table_ref == "tables/t0000.json"


def test_table_sidecar_roundtrip() -> None:
    sidecar = TableSidecar(
        block_index=0,
        layout_type="simple",
        grid_width=2,
        grid={"rows": [{"cells": [TableCell(text="a", colspan=1, rowspan=1)]}]},
        logical_rows=[["a", "b"], ["1", "2"]],
        markdown="| a | b |\n| --- | --- |\n| 1 | 2 |",
        llm_text="【表格:列表】\n--- 行 1 ---\na: 1\nb: 2",
        record_groups=[],
        records=[],
    )
    parsed = TableSidecar.model_validate_json(sidecar.model_dump_json())
    assert parsed.layout_type == "simple"
    assert parsed.slice_status == "missing"
    assert parsed.slice_ref is None


def test_table_sidecar_schema_1_1_slice_fields() -> None:
    sidecar = TableSidecar(
        schema_version="1.1",
        block_index=3,
        slice_ref="tables/t0003.docx",
        slice_status="ok",
        layout_type="simple",
        grid_width=2,
        grid={"rows": []},
        logical_rows=[["a", "b"]],
        markdown="| a | b |",
        llm_text="table",
    )
    parsed = TableSidecar.model_validate_json(sidecar.model_dump_json())
    assert parsed.schema_version == "1.1"
    assert parsed.slice_ref == "tables/t0003.docx"
    assert parsed.slice_status == "ok"


def test_table_sidecar_schema_1_0_defaults_missing_slice() -> None:
    raw = TableSidecar(
        block_index=0,
        layout_type="simple",
        grid_width=1,
        grid={"rows": []},
        logical_rows=[],
        markdown="| a |",
        llm_text="t",
    ).model_dump_json()
    parsed = TableSidecar.model_validate_json(raw)
    assert parsed.schema_version == "1.0"
    assert parsed.slice_ref is None
    assert parsed.slice_status == "missing"
