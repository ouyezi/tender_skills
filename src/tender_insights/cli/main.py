from __future__ import annotations

from pathlib import Path

import typer

from tender_insights.api import extract_templates, interpret_document, resolve_workspace_path, review_legal

app = typer.Typer(name="tender-insights", no_args_is_help=True)


def _resolve(path: Path, output: Path | None, overwrite: bool):
    return resolve_workspace_path(path, output_dir=output, overwrite=overwrite)


@app.command("interpret")
def interpret_cmd(
    path: Path,
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve(path, output, overwrite)
    interpret_document(ws)
    typer.echo(f"Wrote {ws.root / 'interpretation.json'}")


@app.command("template")
def template_cmd(
    path: Path,
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve(path, output, overwrite)
    extract_templates(ws)
    typer.echo(f"Wrote {ws.root / 'templates'}")


@app.command("legal")
def legal_cmd(
    path: Path,
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve(path, output, overwrite)
    review_legal(ws)
    typer.echo(f"Wrote {ws.root / 'legal_review.json'}")


@app.command("all")
def all_cmd(
    path: Path,
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve(path, output, overwrite)
    interpret_document(ws)
    extract_templates(ws)
    review_legal(ws)
