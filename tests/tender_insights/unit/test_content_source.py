from pathlib import Path
from unittest.mock import patch

from doc_chunk.models.outline import OutlineNode, OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.content_source import prepare_interpret_source
from tender_insights.config import InsightsConfig


def test_prepare_interpret_source_writes_file(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    ws.content_path.write_text("# Hello\n\nBody text.\n", encoding="utf-8")
    ws.outline_path.write_text(
        OutlineTree(
            nodes=[
                OutlineNode(
                    node_id="n1",
                    title="Hello",
                    level=1,
                    parent_id=None,
                    sort_order=0,
                    needs_review=False,
                )
            ]
        ).model_dump_json(),
        encoding="utf-8",
    )

    with patch("tender_insights.common.content_source.enrich_content_with_ocr") as mock_enrich:
        mock_enrich.return_value = ("# Hello\n\nBody text.\n", object(), 0)
        source = prepare_interpret_source(ws, config=InsightsConfig(ocr_enabled=True))

    assert source.markdown.startswith("# Hello")
    assert source.source_path.exists()
    mock_enrich.assert_called_once()


def test_prepare_interpret_source_skips_ocr_when_disabled(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=True)
    ws.content_path.write_text("# Hello\n", encoding="utf-8")
    ws.outline_path.write_text(
        OutlineTree(nodes=[]).model_dump_json(),
        encoding="utf-8",
    )

    with patch("tender_insights.common.content_source.enrich_content_with_ocr") as mock_enrich:
        source = prepare_interpret_source(ws, config=InsightsConfig(ocr_enabled=True), ocr_enabled=False)

    assert source.markdown.startswith("# Hello")
    mock_enrich.assert_not_called()
