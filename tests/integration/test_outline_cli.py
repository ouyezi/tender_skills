from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from doc_chunk.cli.main import app
from doc_chunk.workspace.layout import OutputWorkspace


def test_outline_cli_generates_outline_json(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    ws.content_path.write_text("# 第一章\n\n正文\n\n## 第二节\n\n内容", encoding="utf-8")

    result = runner.invoke(app, ["outline", str(ws.root)])

    assert result.exit_code == 0
    outline_path = ws.root / "outline.json"
    assert outline_path.exists()
    outline_data = json.loads(outline_path.read_text(encoding="utf-8"))
    assert outline_data["strategy"] in {
        "toc",
        "heading_heuristic",
        "content_heuristic",
        "flat_fallback",
    }
