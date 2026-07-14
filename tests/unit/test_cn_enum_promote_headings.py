from __future__ import annotations

from pathlib import Path

from docx import Document

from doc_chunk.api import extract_file, extract_outline
from doc_chunk.extract.promote_headings import parse_content_heading_line
from doc_chunk.models.outline import OutlineTree


def test_parse_content_heading_line_cn_enum() -> None:
    assert parse_content_heading_line("二、百福得服务方案介绍") == (1, "二、百福得服务方案介绍")
    assert parse_content_heading_line("  三、项目服务保障能力  ") == (1, "三、项目服务保障能力")
    assert parse_content_heading_line("一、员工投诉反馈机制：") is None
    assert parse_content_heading_line("1、景区门票：接入全国8000多家") is None
    assert parse_content_heading_line("景区门票：接入全国8000多家旅游景点") is None
    assert parse_content_heading_line("1.口腔健康") is None
    assert parse_content_heading_line("1. 技术方案") == (1, "1. 技术方案")
    assert parse_content_heading_line("1\u3000先进的订单管理系统：很长") is None
    assert parse_content_heading_line("1.1企业介绍") == (2, "1.1企业介绍")
    assert parse_content_heading_line("三、 服务费一览表\t4") is None
    assert parse_content_heading_line("2.1 合同条款偏离表（模板）\t2") is None
    assert parse_content_heading_line("普通段落。") is None


def test_promote_headings_auto_promotes_cn_enum(tmp_path: Path) -> None:
    docx_path = tmp_path / "cn_enum.docx"
    doc = Document()
    doc.add_heading("一、企业简介及资质", level=1)
    doc.add_paragraph("1.1 企业介绍")
    doc.add_paragraph("二、百福得服务方案介绍")
    doc.add_paragraph("2.1 企业福利管理的痛点及挑战")
    doc.save(docx_path)

    workspace = tmp_path / "ws"
    extract_file(docx_path, workspace, overwrite=True, promote_headings="auto")
    content_md = (workspace / "content.md").read_text(encoding="utf-8")
    assert "# 一、企业简介及资质" in content_md
    assert "# 二、百福得服务方案介绍" in content_md

    extract_outline(workspace)
    outline = OutlineTree.model_validate_json((workspace / "outline.json").read_text(encoding="utf-8"))
    roots = [node for node in outline.nodes if node.parent_id is None]
    assert len(roots) == 2
    root_titles = {node.title for node in roots}
    assert "一、企业简介及资质" in root_titles
    assert "二、百福得服务方案介绍" in root_titles

    by_title = {node.title: node for node in outline.nodes}
    assert by_title["2.1 企业福利管理的痛点及挑战"].parent_id == by_title["二、百福得服务方案介绍"].node_id
    assert by_title["1.1 企业介绍"].parent_id == by_title["一、企业简介及资质"].node_id


def test_promote_after_decimal_section_keeps_cn_enum_as_paragraph(tmp_path: Path) -> None:
    """Under 7.2-style subsections,「一、…」is local content, not a new L1 chapter."""
    docx_path = tmp_path / "decimal_then_cn_enum.docx"
    doc = Document()
    heading = doc.add_paragraph("7.2丰富的商品资源")
    heading.style = doc.styles["Heading 4"]
    doc.add_paragraph("一、部分合作品牌展示（持续上新）")
    doc.add_paragraph("品牌展示正文。")
    doc.save(docx_path)

    workspace = tmp_path / "ws"
    extract_file(docx_path, workspace, overwrite=True, promote_headings="auto")
    content_md = (workspace / "content.md").read_text(encoding="utf-8")

    assert "#### 7.2丰富的商品资源" in content_md
    assert "# 一、部分合作品牌展示（持续上新）" not in content_md
    assert "一、部分合作品牌展示（持续上新）" in content_md

    from doc_chunk.locate.heading_starts import section_end_by_heading
    import re

    match = re.search(r"^#### 7\.2丰富的商品资源.*$", content_md, re.MULTILINE)
    assert match is not None
    end = section_end_by_heading(content_md, match.start(), 4)
    section = content_md[match.start() : end]
    assert "一、部分合作品牌展示（持续上新）" in section
    assert "品牌展示正文" in section


def test_promote_headings_keeps_local_cn_enum_series_as_paragraphs(tmp_path: Path) -> None:
    docx_path = tmp_path / "local_enum_series.docx"
    doc = Document()
    doc.add_paragraph("2.2.5.2 员工保险")
    doc.add_paragraph("一、员工投诉反馈机制：")
    doc.add_paragraph("投诉处理说明。")
    doc.add_paragraph("二、医疗险索赔流程：")
    doc.add_paragraph("索赔流程说明。")
    doc.add_paragraph("三、索赔及服务问答")
    doc.add_paragraph("问答内容。")
    doc.add_paragraph("四、应急措施")
    doc.add_paragraph("应急说明。")
    doc.save(docx_path)

    workspace = tmp_path / "ws"
    extract_file(docx_path, workspace, overwrite=True, promote_headings="auto")
    content_md = (workspace / "content.md").read_text(encoding="utf-8")
    assert "三、索赔及服务问答" in content_md
    assert "# 三、索赔及服务问答" not in content_md
    assert "# 四、应急措施" not in content_md
    assert "#### 2.2.5.2 员工保险" in content_md

    extract_outline(workspace)
    outline = OutlineTree.model_validate_json((workspace / "outline.json").read_text(encoding="utf-8"))
    roots = [node for node in outline.nodes if node.parent_id is None]
    root_titles = {node.title for node in roots}
    assert "三、索赔及服务问答" not in root_titles
    assert "四、应急措施" not in root_titles
