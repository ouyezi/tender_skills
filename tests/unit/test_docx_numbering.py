from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from doc_chunk.extract.docx_extractor import extract_docx
from doc_chunk.extract.docx_numbering import (
    DocxNumberingResolver,
    _LevelStyle,
    _format_chinese_counting,
    merge_list_prefix,
)
from doc_chunk.workspace.layout import OutputWorkspace


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, "一"),
        (6, "六"),
        (10, "十"),
        (11, "十一"),
        (14, "十四"),
        (20, "二十"),
    ],
)
def test_format_chinese_counting(value: int, expected: str) -> None:
    assert _format_chinese_counting(value) == expected


@pytest.mark.parametrize(
    ("text", "prefix", "expected"),
    [
        ("资格、资信证明文件", "六、", "六、资格、资信证明文件"),
        ("九、供应商类似业绩一览表", "九、", "九、供应商类似业绩一览表"),
        ("四、关于资格的声明函", "四、", "四、关于资格的声明函"),
    ],
)
def test_merge_list_prefix(text: str, prefix: str, expected: str) -> None:
    assert merge_list_prefix(text, prefix) == expected


def test_docx_numbering_resolver_applies_start_value() -> None:
    doc = Document()
    resolver = DocxNumberingResolver(doc)
    resolver._num_to_abstract["2"] = "6"
    resolver._abstract_levels["6"] = {
        0: _LevelStyle(num_fmt="chineseCounting", lvl_text="%1、", start=6),
    }
    paragraph = doc.add_paragraph("资格、资信证明文件", style="Heading 1")
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    p_pr = paragraph._element.get_or_add_pPr()
    num_pr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    num_id = OxmlElement("w:numId")
    num_id.set(qn("w:val"), "2")
    num_pr.append(ilvl)
    num_pr.append(num_id)
    p_pr.append(num_pr)

    assert resolver.advance(paragraph) == "六、"


@pytest.mark.skipif(
    not Path.home().joinpath(
        ".doc-chunk-viewer/uploads/bf3e4dd2-5972-4ff0-af8d-cf0cc947602e/"
        "无锡机电高等职业技术学校-超级礼包2.0-标书.docx"
    ).exists(),
    reason="local tender sample docx not available",
)
def test_extract_docx_restores_heading_list_prefix_from_numpr(tmp_path: Path) -> None:
    docx_path = Path.home() / (
        ".doc-chunk-viewer/uploads/bf3e4dd2-5972-4ff0-af8d-cf0cc947602e/"
        "无锡机电高等职业技术学校-超级礼包2.0-标书.docx"
    )
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    extract_docx(docx_path, ws)
    content = ws.content_path.read_text(encoding="utf-8")

    assert "# 六、资格、资信证明文件" in content
    assert "# 三、分项报价表" in content
