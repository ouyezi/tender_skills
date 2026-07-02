from __future__ import annotations

from pathlib import Path

import pytest
from doc_chunk.api import extract_file, extract_outline
from doc_chunk.outline.toc_docx import extract_docx_toc_outline

CANBU_DOCX = Path.home() / (
    ".doc-chunk-viewer/uploads/c00aa1f9-02e9-4216-927d-64935b99b1ec/【大纲】餐补标书大纲模板6.16.docx"
)


@pytest.mark.skipif(not CANBU_DOCX.exists(), reason="local canbu 6.16 docx not available")
def test_canbu_docx_uses_word_toc_outline() -> None:
    tree = extract_docx_toc_outline(CANBU_DOCX)
    assert tree is not None
    assert tree.strategy == "toc"
    titles = [node.title for node in tree.nodes[:5]]
    assert any("投标函" in title for title in titles)
    assert any("一、" in title for title in titles)
    assert any("2.1" in title and "合同条款偏离表" in title for title in titles)


@pytest.mark.skipif(not CANBU_DOCX.exists(), reason="local canbu 6.16 docx not available")
def test_canbu_pipeline_outline_strategy_is_toc(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    extract_file(CANBU_DOCX, workspace, overwrite=True, promote_headings="auto")
    outline = extract_outline(workspace)
    assert outline.strategy == "toc"
    assert any(node.title.startswith("2.1") for node in outline.nodes)
