from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tender_insights.cli.main import app


def test_cli_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "render" in result.stdout


def test_render_missing_interpretation_exits_1(tmp_path: Path) -> None:
    ws_root = tmp_path / "ws"
    ws_root.mkdir()
    (ws_root / "manifest.json").write_text("{}", encoding="utf-8")
    (ws_root / "content.md").write_text("# x\n", encoding="utf-8")
    (ws_root / "outline.json").write_text(
        json.dumps({"schema_version": "1.0", "strategy": "heading_heuristic", "nodes": []}),
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["render", str(ws_root)])
    assert result.exit_code == 1
