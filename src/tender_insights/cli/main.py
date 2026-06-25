from __future__ import annotations

from pathlib import Path

import typer

from tender_insights.api import (
    extract_templates,
    extract_tender_brief,
    interpret_document,
    prepare_workspaces,
    render_interpretation_report,
    resolve_workspace_path,
    review_legal,
    run_interpret_job,
)
from tender_insights.errors import WorkspaceResolveError

app = typer.Typer(name="tender-insights", no_args_is_help=True)


def _resolve_workspace(path: Path, output: Path | None, overwrite: bool):
    return resolve_workspace_path(path, output_dir=output, overwrite=overwrite)


def _resolve_workspaces(paths: list[Path], output: Path | None, overwrite: bool):
    try:
        return prepare_workspaces(paths, output_dir=output, overwrite=overwrite)
    except WorkspaceResolveError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("interpret")
def interpret_cmd(
    paths: list[Path] = typer.Argument(..., help="工作区目录或原始文档（最多两个文件会自动合并）"),
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve_workspaces(paths, output, overwrite)
    run_interpret_job(ws)
    typer.echo(f"Wrote {ws.root / 'interpretation.json'}")


@app.command("brief")
def brief_cmd(
    paths: list[Path] = typer.Argument(..., help="工作区目录或原始文档（最多两个文件会自动合并）"),
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    """读取招标文件全文，生成标准化招标基础概要（≤500 字）。"""
    ws = _resolve_workspaces(paths, output, overwrite)
    extract_tender_brief(ws)
    typer.echo(f"Wrote {ws.root / 'tender_brief.json'}")
    typer.echo(f"Wrote {ws.root / 'tender_brief.txt'}")


@app.command("template")
def template_cmd(
    path: Path = typer.Argument(..., help="工作区目录"),
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve_workspace(path, output, overwrite)
    extract_templates(ws)
    typer.echo(f"Wrote {ws.root / 'templates'}")


@app.command("legal")
def legal_cmd(
    path: Path = typer.Argument(..., help="工作区目录"),
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve_workspace(path, output, overwrite)
    review_legal(ws)
    typer.echo(f"Wrote {ws.root / 'legal_review.json'}")


@app.command("render")
def render_cmd(
    path: Path = typer.Argument(..., help="含 interpretation.json 的工作区目录"),
    output: Path | None = typer.Option(None, "-o", "--output", help="Markdown 输出路径"),
) -> None:
    ws = _resolve_workspace(path, None, overwrite=False)
    try:
        dest = render_interpretation_report(ws, output_path=output)
    except FileNotFoundError as exc:
        raise typer.Exit(code=1) from exc
    typer.echo(f"Wrote {dest}")


@app.command("all")
def all_cmd(
    paths: list[Path] = typer.Argument(..., help="工作区目录或原始文档（最多两个文件会自动合并）"),
    output: Path | None = typer.Option(None, "-o", "--output"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    ws = _resolve_workspaces(paths, output, overwrite)
    run_interpret_job(ws)
    review_legal(ws)
    typer.echo(f"Wrote {ws.root / 'interpretation.json'}")
    typer.echo(f"Wrote {ws.root / 'templates'}")
    typer.echo(f"Wrote {ws.root / 'legal_review.json'}")
