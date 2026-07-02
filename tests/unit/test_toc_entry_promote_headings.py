from __future__ import annotations

from pathlib import Path

import pytest

from doc_chunk.api import extract_file, extract_outline
from doc_chunk.extract.promote_headings import is_toc_entry_line
from doc_chunk.models.outline import OutlineTree
from viewer.services.section_slice import slice_section


@pytest.mark.parametrize(
    "line",
    [
        "三、 服务费一览表\t4",
        "2.1 合同条款偏离表（模板）\t2",
        "一、 投标函\t1",
    ],
)
def test_is_toc_entry_line(line: str) -> None:
    assert is_toc_entry_line(line)


def test_is_toc_entry_line_rejects_body_heading() -> None:
    assert not is_toc_entry_line("三、 服务费一览表")
    assert not is_toc_entry_line("1. 技术方案")


@pytest.mark.skipif(
    not Path.home().joinpath(
        ".doc-chunk-viewer/uploads/61805407-9bde-4c4d-af88-f7dd91f1a661/【大纲】餐补标书大纲模板6.16.docx"
    ).exists(),
    reason="local tender sample docx not available",
)
def test_promote_auto_section_slice_skips_toc_entries(tmp_path: Path) -> None:
    docx_path = Path.home() / (
        ".doc-chunk-viewer/uploads/61805407-9bde-4c4d-af88-f7dd91f1a661/【大纲】餐补标书大纲模板6.16.docx"
    )
    workspace = tmp_path / "ws"
    extract_file(docx_path, workspace, overwrite=True, promote_headings="auto")
    extract_outline(workspace)
    outline = OutlineTree.model_validate_json((workspace / "outline.json").read_text(encoding="utf-8"))
    content_md = (workspace / "content.md").read_text(encoding="utf-8")

    node = next(node for node in outline.nodes if "服务费一览表" in node.title)
    section = slice_section(content_md, outline, node.node_id)

    assert "table-ref:tables/" in section.markdown
    assert section.char_end - section.char_start > 500
    assert not node.title.endswith("\t4")
