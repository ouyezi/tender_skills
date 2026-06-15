from __future__ import annotations

import json
from pathlib import Path

from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.outline.builder import build_outline_from_workspace
from doc_chunk.workspace.layout import OutputWorkspace


def test_outline_prefers_toc_strategy(monkeypatch, tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    ws.content_path.write_text("# 标题\n\n正文", encoding="utf-8")
    source_path = tmp_path / "a.docx"
    source_path.write_bytes(b"docx")

    toc_tree = OutlineTree(
        strategy="toc",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="目录章节",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
            )
        ],
    )

    monkeypatch.setattr("doc_chunk.outline.builder.extract_docx_toc_outline", lambda _p: toc_tree)
    monkeypatch.setattr("doc_chunk.outline.builder.extract_pdf_bookmark_outline", lambda _p: None)

    tree = build_outline_from_workspace(ws, source_path)

    assert tree.strategy == "toc"
    assert tree.nodes[0].title == "目录章节"
    assert (ws.root / "outline.json").exists()


def test_outline_heading_heuristic_supports_level_1_to_8(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    ws.content_path.write_text(
        "\n\n".join(
            [
                "# 一级",
                "## 二级",
                "### 三级",
                "#### 四级",
                "##### 五级",
                "###### 六级",
                "####### 七级",
                "######## 八级",
            ]
        ),
        encoding="utf-8",
    )

    tree = build_outline_from_workspace(ws, tmp_path / "a.txt")

    assert tree.strategy == "heading_heuristic"
    assert len(tree.nodes) == 8
    assert [node.level for node in tree.nodes] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert tree.nodes[-1].parent_id == tree.nodes[-2].node_id

    outline_data = json.loads((ws.root / "outline.json").read_text(encoding="utf-8"))
    assert outline_data["schema_version"] == "1.0"


def test_outline_falls_back_to_content_heuristic(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    ws.content_path.write_text(
        "第一章 总则\n\n1.1 适用范围\n\n1.1.1 详细说明\n\n普通段落内容。",
        encoding="utf-8",
    )

    tree = build_outline_from_workspace(ws, tmp_path / "a.txt")

    assert tree.strategy == "content_heuristic"
    assert len(tree.nodes) >= 2
    assert all(1 <= node.level <= 8 for node in tree.nodes)


def test_outline_flat_fallback_when_no_structure(tmp_path: Path) -> None:
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    ws.content_path.write_text("这是一段没有结构的正文。", encoding="utf-8")

    tree = build_outline_from_workspace(ws, tmp_path / "招标文件.pdf")

    assert tree.strategy == "flat_fallback"
    assert len(tree.nodes) == 1
    assert tree.nodes[0].level == 1
