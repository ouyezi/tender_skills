from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.template.models import TemplateHitLLM
from tender_insights.template.slicer import slice_template_hit


def test_slicer_rejects_out_of_range(tmp_path) -> None:
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    content_md = "# Test\n\nHello world"
    (ws_dir / "content.md").write_text(content_md, encoding="utf-8")
    workspace = OutputWorkspace.open_existing(ws_dir)
    hit = TemplateHitLLM(
        title="t",
        type="other",
        type_label="其他",
        char_start=-1,
        char_end=10,
        confidence=0.5,
        source_excerpt="",
    )
    assert slice_template_hit(workspace, content_md, hit) is None


def test_slicer_returns_slice_for_valid_hit(tmp_path) -> None:
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    content_md = "# Test\n\nHello world"
    (ws_dir / "content.md").write_text(content_md, encoding="utf-8")
    workspace = OutputWorkspace.open_existing(ws_dir)
    hit = TemplateHitLLM(
        title="t",
        type="other",
        type_label="其他",
        char_start=0,
        char_end=len(content_md),
        confidence=0.9,
        source_excerpt="Hello",
    )
    result = slice_template_hit(workspace, content_md, hit)
    assert result is not None
    md, start, end = result
    assert start == 0
    assert end == len(content_md)
    assert md == content_md.strip()
