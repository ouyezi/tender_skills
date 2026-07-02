from __future__ import annotations

from doc_chunk.outline.toc_docx import build_toc_style_level_map

SAMPLE_STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="16">
    <w:name w:val="toc 1"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="17">
    <w:name w:val="toc 2"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="27">
    <w:name w:val="TOC 标题1"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="toc3">
    <w:name w:val="toc 3"/>
  </w:style>
</w:styles>
""".encode()


def test_build_toc_style_level_map_numeric_style_ids() -> None:
    mapping = build_toc_style_level_map(SAMPLE_STYLES_XML)
    assert mapping["16"] == 1
    assert mapping["17"] == 2
    assert "27" not in mapping
    assert mapping["toc3"] == 3


def test_build_toc_style_level_map_empty_on_missing_styles() -> None:
    assert (
        build_toc_style_level_map(
            b'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
        )
        == {}
    )
