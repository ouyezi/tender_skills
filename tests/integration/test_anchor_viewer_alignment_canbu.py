from __future__ import annotations

from pathlib import Path

import pytest
from doc_chunk.api import extract_file, extract_outline
from viewer.services.section_slice import slice_section

CANBU_DOCX = Path.home() / (
    ".doc-chunk-viewer/uploads/61805407-9bde-4c4d-af88-f7dd91f1a661/【大纲】餐补标书大纲模板6.16.docx"
)


@pytest.mark.skipif(not CANBU_DOCX.exists(), reason="local tender sample docx not available")
def test_all_outline_anchors_match_viewer(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    extract_file(CANBU_DOCX, workspace, overwrite=True, promote_headings="auto")
    outline = extract_outline(workspace)
    content_md = (workspace / "content.md").read_text(encoding="utf-8")

    mismatches: list[str] = []
    for node in outline.nodes:
        section = slice_section(content_md, outline, node.node_id)
        if node.anchor.char_start != section.char_start:
            mismatches.append(
                f"{node.node_id} {node.title!r}: anchor={node.anchor.char_start} viewer={section.char_start}"
            )
    assert not mismatches, "\n".join(mismatches[:10])
