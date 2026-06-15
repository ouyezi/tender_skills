from pathlib import Path

from typer.testing import CliRunner

from doc_chunk.cli.main import app


def test_extract_cli_success(sample_docx: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    out_dir = tmp_path / "out"

    result = runner.invoke(app, ["extract", str(sample_docx), "-o", str(out_dir)])

    assert result.exit_code == 0
    assert (out_dir / "content.md").exists()
    assert (out_dir / "manifest.json").exists()


def test_extract_cli_unsupported_format(tmp_path: Path) -> None:
    runner = CliRunner()
    input_path = tmp_path / "bad.txt"
    input_path.write_text("bad", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = runner.invoke(app, ["extract", str(input_path), "-o", str(out_dir)])

    assert result.exit_code == 4
