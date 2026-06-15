from typer.testing import CliRunner

from doc_chunk.cli.main import app


def test_tree_cli(sample_docx, tmp_path) -> None:
    runner = CliRunner()
    ws = tmp_path / "ws"
    runner.invoke(app, ["extract", str(sample_docx), "-o", str(ws), "--overwrite"])
    runner.invoke(app, ["outline", str(ws)])
    result = runner.invoke(app, ["tree", str(ws)])
    assert result.exit_code == 0
    assert (ws / "document_tree.json").exists()
