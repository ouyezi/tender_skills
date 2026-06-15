from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from doc_chunk.cli.main import app


def test_e2e_workspace_pipeline_and_enrich(sample_docx: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    workspace = tmp_path / "workspace"

    pipeline_result = runner.invoke(
        app,
        ["pipeline", str(sample_docx), "--output", str(workspace), "--skip-enrich"],
    )
    assert pipeline_result.exit_code == 0
    assert (workspace / "chunks" / "index.json").exists()

    enrich_result = runner.invoke(app, ["enrich", str(workspace), "--no-llm"])
    assert enrich_result.exit_code == 0

    index_data = json.loads((workspace / "chunks" / "index.json").read_text(encoding="utf-8"))
    first_chunk_path = workspace / "chunks" / index_data["chunks"][0]["path"]
    first_chunk = json.loads(first_chunk_path.read_text(encoding="utf-8"))
    assert first_chunk["metadata"]["knowledge_type"] is not None
