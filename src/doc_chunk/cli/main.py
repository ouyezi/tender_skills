from __future__ import annotations

from pathlib import Path
import json

import typer

from doc_chunk.api import (
    accept_refined_outline,
    build_tree,
    chunk_document,
    discard_refined_outline,
    enrich_chunks,
    extract_batch,
    extract_file,
    extract_outline,
    refine_outline,
    reset_refined_outline,
    run_pipeline,
)
from doc_chunk.errors import DocChunkError, LLMUnavailableError, UnsupportedFormatError, ValidationError, WorkspaceError

app = typer.Typer(help="Document extraction and chunking for tender skills")


@app.callback()
def main() -> None:
    """doc-chunk command group."""


@app.command("extract")
def extract_command(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    output: Path = typer.Option(..., "--output", "-o"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    promote_headings: str = typer.Option("off", "--promote-headings"),
) -> None:
    try:
        if promote_headings not in {"off", "auto"}:
            raise ValidationError("--promote-headings must be 'off' or 'auto'")
        if input_path.is_dir():
            result = extract_batch(input_path, output, overwrite=overwrite, continue_on_error=True)
            if result.status == "partial_success":
                raise typer.Exit(code=2)
            if result.status == "failed":
                raise typer.Exit(code=1)
            raise typer.Exit(code=0)

        manifest = extract_file(
            input_path,
            output,
            overwrite=overwrite,
            promote_headings=promote_headings,  # type: ignore[arg-type]
        )
        typer.echo(str(output / "manifest.json"))
        if manifest.warnings:
            for warning in manifest.warnings:
                typer.echo(warning, err=True)
        raise typer.Exit(code=0)
    except WorkspaceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except UnsupportedFormatError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=4) from exc
    except DocChunkError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("outline")
def outline_command(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
) -> None:
    try:
        extract_outline(workspace)
        typer.echo(str(workspace / "outline.json"))
        raise typer.Exit(code=0)
    except WorkspaceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except DocChunkError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("tree")
def tree_command(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
) -> None:
    try:
        build_tree(workspace)
        typer.echo(str(workspace / "document_tree.json"))
        raise typer.Exit(code=0)
    except WorkspaceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except DocChunkError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("chunk")
def chunk_command(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    max_tokens: int = typer.Option(20_000, "--max-tokens"),
    use_original: bool = typer.Option(False, "--use-original"),
    markdown_headings_only: bool = typer.Option(False, "--markdown-headings-only"),
) -> None:
    try:
        chunk_document(
            workspace,
            max_tokens=max_tokens,
            use_refined=not use_original,
            markdown_headings_only=markdown_headings_only,
        )
        typer.echo(str(workspace / "chunks" / "index.json"))
        raise typer.Exit(code=0)
    except WorkspaceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except DocChunkError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("refine")
def refine_command(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    instruction: str = typer.Option(..., "--instruction", "-i"),
    lenient: bool = typer.Option(False, "--lenient"),
) -> None:
    try:
        preview = refine_outline(workspace, instruction, strict=not lenient)
        typer.echo(
            json.dumps(
                {
                    "preview": {
                        "node_count_before": preview.node_count_before,
                        "node_count_after": preview.node_count_after,
                        "change_summary": preview.change_summary,
                        "warnings": preview.warnings,
                        "title_diff": preview.title_diff,
                    },
                    "validation": {
                        "passed": preview.validation_passed,
                        "errors": preview.validation_errors,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise typer.Exit(code=0)
    except (WorkspaceError, ValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except LLMUnavailableError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except DocChunkError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("refine-accept")
def refine_accept_command(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
) -> None:
    try:
        accept_refined_outline(workspace)
        typer.echo(str(workspace / "outline_refined.json"))
        raise typer.Exit(code=0)
    except (WorkspaceError, ValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except DocChunkError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("refine-discard")
def refine_discard_command(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
) -> None:
    try:
        discard_refined_outline(workspace)
        raise typer.Exit(code=0)
    except (WorkspaceError, ValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except DocChunkError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("refine-reset")
def refine_reset_command(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    force: bool = typer.Option(False, "--force"),
) -> None:
    try:
        reset_refined_outline(workspace, force=force)
        raise typer.Exit(code=0)
    except WorkspaceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except DocChunkError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("enrich")
def enrich_command(
    workspace: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    no_llm: bool = typer.Option(False, "--no-llm"),
    classification_config: Path | None = typer.Option(None, "--classification-config"),
) -> None:
    try:
        enrich_chunks(
            workspace,
            enable_llm_description=not no_llm,
            classification_config=classification_config,
        )
        typer.echo(str(workspace / "chunks" / "index.json"))
        raise typer.Exit(code=0)
    except WorkspaceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except (LLMUnavailableError, DocChunkError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("pipeline")
def pipeline_command(
    input_path: Path = typer.Argument(..., exists=True, readable=True),
    output: Path = typer.Option(..., "--output", "-o"),
    skip_refine: bool = typer.Option(True, "--skip-refine/--run-refine"),
    skip_enrich: bool = typer.Option(False, "--skip-enrich"),
    refine_instruction: str | None = typer.Option(None, "--refine-instruction"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    max_tokens: int = typer.Option(20_000, "--max-tokens"),
) -> None:
    try:
        result = run_pipeline(
            input_path,
            output,
            overwrite=overwrite,
            skip_refine=skip_refine,
            skip_enrich=skip_enrich,
            refine_instruction=refine_instruction,
            max_tokens=max_tokens,
            continue_on_error=True,
        )
        if result.status == "partial_success":
            raise typer.Exit(code=2)
        if result.status == "failed":
            raise typer.Exit(code=1)
        raise typer.Exit(code=0)
    except WorkspaceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3) from exc
    except UnsupportedFormatError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=4) from exc
    except DocChunkError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
