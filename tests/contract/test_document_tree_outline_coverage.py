from __future__ import annotations

import json
from pathlib import Path

import pytest

from doc_chunk.api import build_tree, chunk_document, extract_file, extract_outline
from tests.fixtures.anchor_fixture_factory import ensure_anchor_fixtures, patch_outline_anchor_on_block

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="module", autouse=True)
def _ensure_fixtures() -> None:
    ensure_anchor_fixtures()


@pytest.mark.parametrize(
    ("docx_name", "block_index"),
    [
        ("outline_anchor_on_image.docx", 0),
        ("outline_anchor_on_table.docx", 0),
    ],
)
def test_document_tree_covers_all_outline_nodes(tmp_path: Path, docx_name: str, block_index: int) -> None:
    src = FIXTURES / docx_name
    ws = tmp_path / docx_name.replace(".docx", "")
    extract_file(src, ws, overwrite=True)
    extract_outline(ws)
    patch_outline_anchor_on_block(ws, outline_titles=["封面", "第二章"], block_index=block_index)
    build_tree(ws)
    chunk_document(ws, use_refined=False)

    outline = json.loads((ws / "outline.json").read_text(encoding="utf-8"))["nodes"]
    tree = json.loads((ws / "document_tree.json").read_text(encoding="utf-8"))["nodes"]
    linkage = json.loads((ws / "linkage.json").read_text(encoding="utf-8"))["entries"]

    outline_ids = {node["node_id"] for node in outline}
    assert len(outline) >= 2
    node_ids = [node["node_id"] for node in tree]
    assert len(node_ids) == len(set(node_ids))
    heading_outline = {
        node["outline_node_id"]
        for node in tree
        if node["node_type"] == "heading" and node.get("outline_node_id")
    }
    assert heading_outline == outline_ids
    assert len(linkage) == len(outline_ids)
    assert all(entry["document_tree_node_ids"] for entry in linkage)
