from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from doc_chunk.cli.main import app
from doc_chunk.workspace.layout import OutputWorkspace


def _prepare_workspace(root: Path) -> OutputWorkspace:
    ws = OutputWorkspace.create(root, overwrite=False)
    ws.content_path.write_text("# 第一章\n\n正文", encoding="utf-8")
    ws.outline_path.write_text(
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
    (ws.root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "status": "success",
                "source": {
                    "path": str(ws.root / "sample.docx"),
                    "file_name": "sample.docx",
                    "file_type": "docx",
                    "title": "sample",
                },
                "stages": {"extract": {"status": "success", "warnings": []}},
                "outputs": {},
                "warnings": [],
                "errors": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ws


def test_refine_accept_discard_reset_cli(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    ws = _prepare_workspace(tmp_path / "ws")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        "doc_chunk.api.create_llm_client_from_env",
        lambda: __import__("doc_chunk.llm.client", fromlist=["FakeLLMClient"]).FakeLLMClient(
            responses=[
                (
                    '{"outline_refined":{"schema_version":"1.0","strategy":"heading_heuristic","nodes":[{"node_id":"r1",'
                    '"title":"优化第一章","level":1,"parent_id":null,"sort_order":0,"anchor":{"block_index":0},"needs_review":false,"source_refs":["n1"]}],'
                    '"derived_from":null,"accepted_at":null},"node_mappings":[{"refined_node_id":"r1","source_node_ids":["n1"],'
                    '"markdown_range":{"char_start":0,"char_end":8},"operation":"rename"}],"change_summary":"重命名章节"}'
                )
            ]
        ),
    )

    refine_result = runner.invoke(app, ["refine", str(ws.root), "-i", "重命名章节"])
    assert refine_result.exit_code == 0
    assert '"passed": true' in refine_result.stdout

    accept_result = runner.invoke(app, ["refine-accept", str(ws.root)])
    assert accept_result.exit_code == 0
    assert ws.outline_refined_path.exists()
    assert ws.outline_mapping_path.exists()

    discard_result = runner.invoke(app, ["refine-discard", str(ws.root)])
    assert discard_result.exit_code == 3

    reset_result = runner.invoke(app, ["refine-reset", str(ws.root), "--force"])
    assert reset_result.exit_code == 0
    assert not ws.outline_refined_path.exists()
