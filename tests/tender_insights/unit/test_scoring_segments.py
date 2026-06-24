import json

from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.table_model import TableSidecar, TablesIndex, TablesIndexEntry
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.scoring_segments import (
    build_scoring_table_segments,
    inject_scoring_tables_into_markdown,
    is_scoring_section_path,
    is_scoring_table_llm_text,
)


def test_is_scoring_section_path() -> None:
    assert is_scoring_section_path(["第三章 评审办法", "5.2 评分"])
    assert not is_scoring_section_path(["第一章 总则"])


def test_is_scoring_table_llm_text() -> None:
    text = "【表格: 评分表】\n评分说明 | 分值\n商品方案契合度 | 0-2分"
    assert is_scoring_table_llm_text(text)
    assert not is_scoring_table_llm_text("【表格: 人员表】\n姓名 | 职务")


def test_inject_scoring_tables_into_markdown(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    table_path = ws.tables_dir / "t-001.json"
    llm_text = "【表格: 评分表】\n商品方案 | 0-2分"
    sidecar = TableSidecar(
        block_index=1,
        layout_type="simple",
        grid_width=2,
        grid={},
        markdown="| 商品方案 | 0-2分 |",
        llm_text=llm_text,
    )
    table_path.write_text(sidecar.model_dump_json(), encoding="utf-8")

    content_md = "# 5.2 评分\n\n采购人：某某\n\n| placeholder |\n"
    ws.content_path.write_text(content_md, encoding="utf-8")
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=0,
                block_type="heading",
                char_start=0,
                char_end=10,
            ),
            ContentBlockRecord(
                block_index=1,
                block_type="table",
                char_start=20,
                char_end=40,
                table_ref="tables/t-001.json",
            ),
        ]
    )
    ws.content_blocks_path.write_text(blocks.model_dump_json(), encoding="utf-8")
    ws.tables_index_path.write_text(
        TablesIndex(tables=[TablesIndexEntry(block_index=1, path="tables/t-001.json")]).model_dump_json(),
        encoding="utf-8",
    )

    injected = inject_scoring_tables_into_markdown(
        ws,
        markdown="采购人：某某",
        char_start=10,
        char_end=40,
        blocks=blocks,
    )
    assert "商品方案" in injected
    assert "0-2分" in injected


def test_build_scoring_table_segments_caps_at_five(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    blocks_entries: list[ContentBlockRecord] = []
    index_entries: list[TablesIndexEntry] = []
    for i in range(7):
        ref = f"tables/t-{i:03d}.json"
        llm_text = f"【表格: 评分表{i}】\n评分说明 | 分值\n行 | 0-{i}分"
        (ws.tables_dir / f"t-{i:03d}.json").write_text(
            TableSidecar(
                block_index=i,
                layout_type="simple",
                grid_width=2,
                grid={},
                markdown="md",
                llm_text=llm_text,
            ).model_dump_json(),
            encoding="utf-8",
        )
        blocks_entries.append(
            ContentBlockRecord(
                block_index=i,
                block_type="table",
                char_start=i * 100,
                char_end=i * 100 + 50,
                table_ref=ref,
            )
        )
        index_entries.append(TablesIndexEntry(block_index=i, path=ref))

    blocks = ContentBlocksFile(blocks=blocks_entries)
    ws.content_blocks_path.write_text(blocks.model_dump_json(), encoding="utf-8")
    ws.tables_index_path.write_text(TablesIndex(tables=index_entries).model_dump_json(), encoding="utf-8")

    segments = build_scoring_table_segments(
        ws,
        blocks=blocks,
        host_section_path=["第六章 响应文件格式"],
        max_segments=5,
    )
    assert len(segments) == 5
    assert segments[0].segment_id == "seg-scoring-001"
    assert "0-0分" in segments[0].markdown
