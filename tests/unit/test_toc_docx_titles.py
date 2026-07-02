from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from doc_chunk.outline.toc_docx import _join_toc_text_parts, extract_docx_toc_outline


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (["1", "投标函", "11"], "1 投标函"),
        (["2.1", "合同条款偏离表", "12"], "2.1 合同条款偏离表"),
        (["2.1 合同条款偏离表", "12"], "2.1 合同条款偏离表"),
        (["1 投标函", "11"], "1 投标函"),
        (["评分索引表", "10"], "评分索引表"),
        (["评分索引表10"], "评分索引表"),
        (["1投标函11"], "1 投标函"),
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
    assert titles == ["评分索引表", "1 投标函", "2 服务偏离表", "2.1 合同条款偏离表", "2.2 技术条款偏离表"]


def _minimal_docx_with_numeric_toc_styles(tmp_path: Path) -> Path:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def p(style: str, texts: list[str], instr: str | None = None) -> str:
        runs = ""
        if instr:
            runs += f'<w:r><w:instrText xml:space="preserve">{instr}</w:instrText></w:r>'
        for text in texts:
            runs += f"<w:r><w:t>{text}</w:t></w:r>"
        return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{runs}</w:p>'

    body = (
        p("16", ["一、 投标函", "1"], ' TOC \\o "1-3" \\h \\u ')
        + p("16", ["二、 服务偏离表", "2"], " HYPERLINK \\l _Toc1 ")
        + p("17", ["2.1 ", "合同条款偏离表", "2"], " HYPERLINK \\l _Toc2 ")
    )
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>""".encode()
    styles_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{ns}">
  <w:style w:type="paragraph" w:styleId="16"><w:name w:val="toc 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="17"><w:name w:val="toc 2"/></w:style>
</w:styles>""".encode()

    docx_path = tmp_path / "numeric-toc.docx"
    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            b'<Default Extension="xml" ContentType="application/xml"/>'
            b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            b'<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            b"</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            b"</Relationships>",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            b"</Relationships>",
        )
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", styles_xml)
    docx_path.write_bytes(buf.getvalue())
    return docx_path


def test_extract_docx_toc_outline_numeric_style_ids(tmp_path: Path) -> None:
    docx_path = _minimal_docx_with_numeric_toc_styles(tmp_path)
    tree = extract_docx_toc_outline(docx_path)
    assert tree is not None
    assert tree.strategy == "toc"
    titles = [node.title for node in tree.nodes]
    assert titles[0] == "一、 投标函"
    assert titles[2].startswith("2.1 ")
    assert titles[2].startswith("2.1 合同")
