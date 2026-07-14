from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from doc_chunk.api import extract_file


def _docx_with_toc_and_body(tmp_path: Path) -> Path:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = (
        f'<w:p><w:pPr><w:pStyle w:val="20"/></w:pPr>'
        f'<w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\u </w:instrText></w:r>'
        f'<w:r><w:t>一、服务方案1</w:t></w:r></w:p>'
        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        f'<w:r><w:t>一、服务方案</w:t></w:r></w:p>'
        f'<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
        f'<w:r><w:t>正文段落</w:t></w:r></w:p>'
    )
    document_xml = (
        f'<?xml version="1.0"?><w:document xmlns:w="{ns}">'
        f"<w:body>{body}</w:body></w:document>"
    ).encode()
    styles_xml = f"""<?xml version="1.0"?>
<w:styles xmlns:w="{ns}">
  <w:style w:type="paragraph" w:styleId="Normal" w:default="1"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="20"><w:name w:val="toc 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/></w:style>
</w:styles>""".encode()
    path = tmp_path / "toc-style.docx"
    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            b'<Default Extension="xml" ContentType="application/xml"/>'
            b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            b'<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            b'<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
            b"</Types>",
        )
        z.writestr(
            "_rels/.rels",
            b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            b"</Relationships>",
        )
        z.writestr(
            "word/_rels/document.xml.rels",
            b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
            b"</Relationships>",
        )
        z.writestr(
            "word/numbering.xml",
            b'<?xml version="1.0"?>'
            b'<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>',
        )
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/styles.xml", styles_xml)
    path.write_bytes(buf.getvalue())
    return path


def test_extract_skips_toc_style_as_heading(tmp_path: Path) -> None:
    src = _docx_with_toc_and_body(tmp_path)
    ws = tmp_path / "ws"
    extract_file(src, ws, overwrite=True)
    md = (ws / "content.md").read_text(encoding="utf-8")
    assert "# 一、服务方案1" not in md
    assert "一、服务方案1" in md
    assert md.count("# 一、服务方案") == 1
