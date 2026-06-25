from __future__ import annotations

import json
from pathlib import Path

from tender_insights.common.workspace_merge import merge_workspaces, validate_merged_workspace


def _write_minimal_workspace(
    root: Path,
    *,
    content: str,
    nodes: list[dict],
    images: dict[str, bytes] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "content.md").write_text(content, encoding="utf-8")
    outline = {
        "schema_version": "1.0",
        "strategy": "heading_heuristic",
        "nodes": nodes,
    }
    (root / "outline.json").write_text(json.dumps(outline), encoding="utf-8")
    if images:
        img_dir = root / "images"
        img_dir.mkdir(exist_ok=True)
        for name, data in images.items():
            (img_dir / name).write_bytes(data)
    return root


def test_merge_offsets_second_file_nodes(tmp_path: Path) -> None:
    ws1 = _write_minimal_workspace(
        tmp_path / "ws1",
        content="# A\n\nalpha",
        nodes=[
            {
                "node_id": "n-001",
                "title": "A",
                "level": 1,
                "parent_id": None,
                "sort_order": 0,
                "anchor": {"char_start": 0, "char_end": 10},
            }
        ],
    )
    ws2 = _write_minimal_workspace(
        tmp_path / "ws2",
        content="# B\n\nbeta",
        nodes=[
            {
                "node_id": "n-001",
                "title": "B",
                "level": 1,
                "parent_id": None,
                "sort_order": 0,
                "anchor": {"char_start": 0, "char_end": 9},
            }
        ],
    )
    target = tmp_path / "merged"
    merge_workspaces(
        target,
        sources=[(ws1, "file1.docx"), (ws2, "file2.docx")],
    )
    merged_content = (target / "content.md").read_text(encoding="utf-8")
    assert merged_content.startswith("# A\n\nalpha")
    assert "<!-- source: file2.docx -->" in merged_content
    assert "beta" in merged_content

    outline = json.loads((target / "outline.json").read_text(encoding="utf-8"))
    node_ids = {n["node_id"] for n in outline["nodes"]}
    assert "n-001" in node_ids
    assert "m2:n-001" in node_ids

    m2 = next(n for n in outline["nodes"] if n["node_id"] == "m2:n-001")
    offset = len("# A\n\nalpha\n\n<!-- source: file2.docx -->\n")
    assert m2["anchor"]["char_start"] == 0 + offset
    validate_merged_workspace(target)


def test_merge_renames_conflicting_images(tmp_path: Path) -> None:
    ws1 = _write_minimal_workspace(
        tmp_path / "ws1",
        content="![a](images/logo.png)",
        nodes=[],
        images={"logo.png": b"1"},
    )
    ws2 = _write_minimal_workspace(
        tmp_path / "ws2",
        content="![b](images/logo.png)",
        nodes=[],
        images={"logo.png": b"2"},
    )
    target = tmp_path / "merged"
    merge_workspaces(target, sources=[(ws1, "a.docx"), (ws2, "b.docx")])
    assert (target / "images" / "logo.png").read_bytes() == b"1"
    assert (target / "images" / "m2_logo.png").read_bytes() == b"2"
    content = (target / "content.md").read_text(encoding="utf-8")
    assert "images/m2_logo.png" in content.split("<!-- source:")[1]
