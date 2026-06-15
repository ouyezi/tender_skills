from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from doc_chunk.api import run_pipeline
from doc_chunk.cli.main import app


def test_run_pipeline_single_file(sample_docx: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "out"
    result = run_pipeline(sample_docx, workspace, skip_enrich=True)
    assert result.status == "success"
    assert (workspace / "content.md").exists()
    assert (workspace / "outline.json").exists()
    assert (workspace / "chunks" / "index.json").exists()


def test_pipeline_cli_batch_returns_partial_success(tmp_path: Path) -> None:
    runner = CliRunner()
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "bad.txt").write_text("bad", encoding="utf-8")
    output = tmp_path / "out"

    result = runner.invoke(app, ["pipeline", str(input_dir), "--output", str(output)])
    assert result.exit_code == 1
