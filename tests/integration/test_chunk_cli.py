from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from doc_chunk.cli.main import app
from doc_chunk.workspace.layout import OutputWorkspace


def test_chunk_cli_writes_chunk_files(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    ws.content_path.write_text("# 第一章\n\n正文", encoding="utf-8")
    (ws.root / "outline.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy": "heading_heuristic",
                "nodes": [
                    {
                        "node_id": "n1",
                        "title": "第一章",
                        "level": 1,
                        "parent_id": None,
                        "sort_order": 0,
                        "anchor": {"block_index": 0},
                        "needs_review": False,
                        "source_refs": [],
                    }
                ],
                "derived_from": None,
                "accepted_at": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["chunk", str(ws.root), "--max-tokens", "100"])

    assert result.exit_code == 0
    assert (ws.chunks_dir / "index.json").exists()
    assert (ws.chunks_dir / "chunk-0001.json").exists()


def test_chunk_cli_use_original_overrides_refined(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    ws.content_path.write_text("# 第一章\n\n正文", encoding="utf-8")

    original_outline = {
        "schema_version": "1.0",
        "strategy": "heading_heuristic",
        "nodes": [
            {
                "node_id": "n1",
                "title": "第一章",
                "level": 1,
                "parent_id": None,
                "sort_order": 0,
                "anchor": {"block_index": 0},
                "needs_review": False,
                "source_refs": [],
            }
        ],
        "derived_from": None,
        "accepted_at": None,
    }
    refined_outline = {
        **original_outline,
        "nodes": [
            {
                "node_id": "rn1",
                "title": "优化后的章节",
                "level": 1,
                "parent_id": None,
                "sort_order": 0,
                "anchor": {"block_index": 0},
                "needs_review": False,
                "source_refs": ["n1"],
            }
        ],
        "derived_from": "outline.json",
    }
    (ws.root / "outline.json").write_text(json.dumps(original_outline, ensure_ascii=False), encoding="utf-8")
    (ws.root / "outline_refined.json").write_text(
        json.dumps(refined_outline, ensure_ascii=False), encoding="utf-8"
    )

    result = runner.invoke(app, ["chunk", str(ws.root), "--use-original"])

    assert result.exit_code == 0
    index_data = json.loads((ws.chunks_dir / "index.json").read_text(encoding="utf-8"))
    assert index_data["outline_source"] == "original"
