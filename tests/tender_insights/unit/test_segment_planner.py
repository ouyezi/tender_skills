from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.outline import OutlineNode, OutlineTree
from doc_chunk.models.table_model import TableSidecar, TablesIndex, TablesIndexEntry
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.content_source import InterpretSource
from tender_insights.common.scoring_segments import is_scoring_section_path
from tender_insights.common.segment_planner import plan_segments
from tender_insights.config import InsightsConfig


def _write_outline(ws: OutputWorkspace) -> None:
    tree = OutlineTree(
        nodes=[
            OutlineNode(
                node_id="n1",
                title="Section A",
                level=1,
                parent_id=None,
                sort_order=0,
                needs_review=False,
            ),
            OutlineNode(
                node_id="n2",
                title="Section B",
                level=1,
                parent_id=None,
                sort_order=1,
                needs_review=False,
            ),
        ]
    )
    ws.outline_path.write_text(tree.model_dump_json(), encoding="utf-8")


def test_plan_segments_single_section(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    md = "# Section A\n\nShort body.\n"
    ws.content_path.write_text(md, encoding="utf-8")
    _write_outline(ws)
    source = InterpretSource(markdown=md, source_path=ws.content_path, blocks=None, ocr_image_count=0)
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))

    segments = plan_segments(
        ws,
        source,
        outline,
        config=InsightsConfig(segment_min_tokens=10, segment_max_tokens=5000),
    )
    assert len(segments) >= 1
    assert segments[0].segment_id.startswith("seg-")


def test_plan_segments_splits_oversized(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    body = "line\n" * 5000
    md = f"# Big\n\n{body}"
    ws.content_path.write_text(md, encoding="utf-8")
    _write_outline(ws)
    source = InterpretSource(markdown=md, source_path=ws.content_path, blocks=None, ocr_image_count=0)
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))

    segments = plan_segments(
        ws,
        source,
        outline,
        config=InsightsConfig(segment_min_tokens=100, segment_max_tokens=500),
    )
    assert len(segments) >= 2


def test_plan_segments_injects_scoring_table_into_short_section(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    ref = "tables/t-001.json"
    llm_text = "【表格: 评分表】\n商品方案契合度 | 0-2分"
    (ws.tables_dir / "t-001.json").write_text(
        TableSidecar(
            block_index=1,
            layout_type="simple",
            grid_width=2,
            grid={},
            markdown="| md |",
            llm_text=llm_text,
        ).model_dump_json(),
        encoding="utf-8",
    )
    md = "# 第三章 评审办法\n\n## 5.2 评分\n\n采购人：测试\n\n| t |\n"
    ws.content_path.write_text(md, encoding="utf-8")
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=1,
                block_type="table",
                char_start=30,
                char_end=50,
                table_ref=ref,
            )
        ]
    )
    ws.content_blocks_path.write_text(blocks.model_dump_json(), encoding="utf-8")
    ws.tables_index_path.write_text(
        TablesIndex(tables=[TablesIndexEntry(block_index=1, path=ref)]).model_dump_json(),
        encoding="utf-8",
    )
    _write_outline(ws)
    source = InterpretSource(markdown=md, source_path=ws.content_path, blocks=blocks, ocr_image_count=0)
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))

    segments = plan_segments(
        ws,
        source,
        outline,
        config=InsightsConfig(
            segment_min_tokens=10,
            segment_max_tokens=5000,
            segment_keyword_match_enabled=True,
        ),
    )
    scoring_seg = next(
        s for s in segments if is_scoring_section_path(s.section_path) or "商品方案" in s.markdown
    )
    assert "商品方案" in scoring_seg.markdown
    assert "0-2分" in scoring_seg.markdown


def test_plan_segments_merges_small_segment_with_following(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    md = "# Tiny\n\nhi\n\n# Big\n\n" + ("word " * 200)
    ws.content_path.write_text(md, encoding="utf-8")
    _write_outline(ws)
    source = InterpretSource(markdown=md, source_path=ws.content_path, blocks=None, ocr_image_count=0)
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))

    segments = plan_segments(
        ws,
        source,
        outline,
        config=InsightsConfig(segment_min_tokens=50, segment_max_tokens=5000),
    )
    merged = next(s for s in segments if "hi" in s.markdown and "word" in s.markdown)
    assert merged.char_start == 0


def test_plan_segments_merges_short_heading_with_next_section(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    body = "采购文件\n\n" + ("须知正文 " * 80)
    md = f"# 第二章 响应人须知\n\n## 采购文件\n\n{body}"
    ws.content_path.write_text(md, encoding="utf-8")
    _write_outline(ws)
    source = InterpretSource(markdown=md, source_path=ws.content_path, blocks=None, ocr_image_count=0)
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))

    segments = plan_segments(
        ws,
        source,
        outline,
        config=InsightsConfig(segment_min_tokens=50, segment_max_tokens=5000),
    )
    assert any("须知正文" in s.markdown for s in segments)
    assert not any(s.markdown.strip() == "采购文件" for s in segments)


def test_plan_segments_appends_scoring_dedicated_segments(tmp_path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    ref = "tables/t-001.json"
    llm_text = "【表格: 评分表】\n评分说明 | 分值\n仓储方案 | 0-3分"
    (ws.tables_dir / "t-001.json").write_text(
        TableSidecar(
            block_index=1,
            layout_type="simple",
            grid_width=2,
            grid={},
            markdown="md",
            llm_text=llm_text,
        ).model_dump_json(),
        encoding="utf-8",
    )
    md = "# 第六章 响应文件格式\n\n正文混排\n\n| t |\n"
    ws.content_path.write_text(md, encoding="utf-8")
    blocks = ContentBlocksFile(
        blocks=[
            ContentBlockRecord(
                block_index=1,
                block_type="table",
                char_start=20,
                char_end=40,
                table_ref=ref,
            )
        ]
    )
    ws.content_blocks_path.write_text(blocks.model_dump_json(), encoding="utf-8")
    ws.tables_index_path.write_text(
        TablesIndex(tables=[TablesIndexEntry(block_index=1, path=ref)]).model_dump_json(),
        encoding="utf-8",
    )
    _write_outline(ws)
    source = InterpretSource(markdown=md, source_path=ws.content_path, blocks=blocks, ocr_image_count=0)
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))

    segments = plan_segments(
        ws,
        source,
        outline,
        config=InsightsConfig(
            segment_min_tokens=10,
            segment_max_tokens=5000,
            segment_keyword_match_enabled=True,
        ),
    )
    dedicated = [s for s in segments if s.segment_id.startswith("seg-scoring-")]
    assert len(dedicated) == 1
    assert "仓储方案" in dedicated[0].markdown
