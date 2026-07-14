from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from doc_chunk.outline.toc_docx import extract_docx_toc_outline


def _minimal_docx_with_hyperlink_toc(tmp_path: Path) -> Path:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def p(style: str, texts: list[str], instr: str | None = None) -> str:
        runs = ""
        if instr:
            runs += f'<w:r><w:instrText xml:space="preserve">{instr}</w:instrText></w:r>'
        for text in texts:
            runs += f"<w:r><w:t>{text}</w:t></w:r>"
        return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{runs}</w:p>'

    body = (
        p("16", ["目录"], ' TOC \\o "1-3" \\h \\u ')
        + p("16", ["一、服务方案", "1"], " HYPERLINK \\l _Toc7154 ")
    )
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>""".encode()
    styles_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{ns}">
  <w:style w:type="paragraph" w:styleId="16"><w:name w:val="toc 1"/></w:style>
</w:styles>""".encode()

    docx_path = tmp_path / "hyperlink-toc.docx"
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


def test_extract_docx_toc_outline_records_bookmark_ref(tmp_path: Path) -> None:
    path = _minimal_docx_with_hyperlink_toc(tmp_path)
    tree = extract_docx_toc_outline(path)
    assert tree is not None
    node = next(n for n in tree.nodes if "服务方案" in n.title)
    assert any(ref.startswith("toc_bookmark:") for ref in node.source_refs)
    assert "toc_bookmark:_Toc7154" in node.source_refs
