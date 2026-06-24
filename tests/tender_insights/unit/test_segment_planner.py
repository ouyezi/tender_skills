from doc_chunk.models.outline import OutlineNode, OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.content_source import InterpretSource
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
