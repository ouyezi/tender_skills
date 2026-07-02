from __future__ import annotations

from pathlib import Path

import pytest

from doc_chunk.outline.toc_docx import _join_toc_text_parts, extract_docx_toc_outline


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (["1", "投标函", "11"], "1投标函"),
        (["2.1", "合同条款偏离表", "12"], "2.1合同条款偏离表"),
        (["评分索引表", "10"], "评分索引表"),
        (["评分索引表10"], "评分索引表"),
        (["1投标函11"], "1投标函"),
    ],
)
def test_join_toc_text_parts(parts: list[str], expected: str) -> None:
    assert _join_toc_text_parts(parts) == expected


@pytest.mark.skipif(
    not Path.home().joinpath(
        ".doc-chunk-viewer/uploads/070b4127-d733-4c58-bdcd-3ce8e08d9f2c/超2-FY25春节档期标书模板.docx"
    ).exists(),
    reason="local tender sample docx not available",
)
def test_extract_docx_toc_outline_strips_page_numbers() -> None:
    docx_path = Path.home() / (
        ".doc-chunk-viewer/uploads/070b4127-d733-4c58-bdcd-3ce8e08d9f2c/超2-FY25春节档期标书模板.docx"
    )
    tree = extract_docx_toc_outline(docx_path)
    assert tree is not None
    titles = [node.title for node in tree.nodes[:5]]
    assert titles == ["评分索引表", "1投标函", "2服务偏离表", "2.1合同条款偏离表", "2.2技术条款偏离表"]
