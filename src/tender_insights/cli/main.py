from __future__ import annotations

from pathlib import Path

import typer

from tender_insights.api import (
    accept_gen_catalog,
    continue_gen_catalog,
    extract_templates,
    extract_tender_brief,
    interpret_document,
    prepare_workspaces,
    render_interpretation_report,
    resolve_workspace_path,
    review_legal,
    run_bid_diagnose_job,
    run_bid_summary_job,
    run_gen_catalog_job,
    run_interpret_job,
    run_summary_loop_job,
)
from tender_insights.bid_diagnose.models import BidDiagnosePrerequisiteError
from tender_insights.diagnosis.models import DiagnosisPrerequisiteError
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


@app.command("gen-catalog")
def gen_catalog_cmd(
    path: Path = typer.Argument(..., help="含 interpretation.json 的工作区目录"),
    step: bool = typer.Option(False, "--step", help="按步模式"),
    once: bool = typer.Option(False, "--once", help="只执行下一步后暂停"),
    continue_: bool = typer.Option(False, "--continue", help="从 session 暂停处继续"),
    accept: bool = typer.Option(False, "--accept", help="确认 draft 落盘"),
    restart: bool = typer.Option(False, "--restart", help="清除 gen_catalog 状态重新开始"),
    overwrite: bool = typer.Option(False, "--overwrite", help="覆盖已有 bid_outline.json"),
) -> None:
    ws = _resolve_workspace(path, None, overwrite=False)
    if accept:
        accept_gen_catalog(ws)
        typer.echo(f"Wrote {ws.root / 'bid_outline.json'}")
        return

    mode = "step" if step or once or continue_ else "auto"
    run_limit = 1 if (once and not continue_) or continue_ else None
    run_gen_catalog_job(
        ws,
        mode=mode,
        continue_from_session=continue_,
        restart=restart,
        overwrite=overwrite,
        run_limit=run_limit,
    )
    typer.echo(f"Wrote {ws.root / 'bid_outline.draft.json'}")


@app.command("loop")
def loop_cmd(
    paths: list[Path] = typer.Argument(..., help="工作区目录或原始文档"),
    output: Path | None = typer.Option(None, "-o", "--output"),
    background: str = typer.Option(..., "--background", help="任务背景描述"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    timeout: int | None = typer.Option(None, "--timeout", help="单次 invoke 超时秒数，默认 600"),
) -> None:
    ws = _resolve_workspaces(paths, output, overwrite)
    result = run_summary_loop_job(
        ws,
        task_background=background,
        overwrite=overwrite,
        timeout_s=timeout,
    )
    loop_dir = ws.root / "summary_loop"
    if result.status != "completed":
        typer.echo(f"Summary loop failed at step {result.failed_step}: {result.error_message}", err=True)
        typer.echo(f"Partial results written to {loop_dir}")
        raise typer.Exit(code=1)
    typer.echo(f"Wrote {loop_dir / 'results.json'}")
    typer.echo(f"Wrote {loop_dir / 'report.md'}")


@app.command("bid-summary", help="对标书分段滚动总结（需 summary_loop/report.md 与 chunks/）")
def bid_summary_cmd(
    path: Path = typer.Argument(..., help="已有工作区目录（须含 summary_loop/report.md 与 chunks/）"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    timeout: int | None = typer.Option(None, "--timeout", help="单次 invoke 超时秒数，默认 600"),
) -> None:
    ws = _resolve_workspace(path, None, overwrite=False)
    try:
        result = run_bid_summary_job(ws, overwrite=overwrite, timeout_s=timeout)
    except DiagnosisPrerequisiteError as exc:
        raise typer.BadParameter(str(exc)) from exc

    summary_dir = ws.root / "bid_summary"
    if result.status != "completed":
        typer.echo(
            f"标书总结失败，停在分段 {result.failed_segment}: {result.error_message}",
            err=True,
        )
        typer.echo(f"Partial results written to {summary_dir}")
        raise typer.Exit(code=1)
    typer.echo(f"Wrote {summary_dir / 'total_summary.md'}")
    typer.echo(f"Wrote {summary_dir / 'sec_in_total.json'}")
    typer.echo(f"Wrote {summary_dir / 'run_state.json'}")


@app.command("bid-diagnose", help="对标书分片滚动诊断（需 bid_summary/ 已完成）")
def bid_diagnose_cmd(
    path: Path = typer.Argument(..., help="已有工作区目录（须含 bid_summary/ 与 chunks/）"),
    background: str = typer.Option("", "--background", help="bid_background，可为空"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    timeout: int | None = typer.Option(None, "--timeout", help="单次 invoke 超时秒数，默认 600"),
) -> None:
    ws = _resolve_workspace(path, None, overwrite=False)
    try:
        result = run_bid_diagnose_job(
            ws,
            bid_background=background,
            overwrite=overwrite,
            timeout_s=timeout,
        )
    except BidDiagnosePrerequisiteError as exc:
        raise typer.BadParameter(str(exc)) from exc

    diag_dir = ws.root / "bid_diagnose"
    if result.status != "completed":
        typer.echo(
            f"标书诊断失败，停在分段 {result.failed_segment} / 任务 {result.failed_task}: "
            f"{result.error_message}",
            err=True,
        )
        typer.echo(f"Partial results written to {diag_dir}")
        raise typer.Exit(code=1)
    typer.echo(f"Wrote {diag_dir / 'diagnose_result.md'}")
    typer.echo(f"Wrote {diag_dir / 'run_state.json'}")


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
