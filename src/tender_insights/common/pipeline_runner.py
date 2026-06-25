from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from doc_chunk.api import run_pipeline
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.workspace_merge import merge_workspaces, validate_merged_workspace
from tender_insights.errors import WorkspaceResolveError


def _is_workspace(path: Path) -> bool:
    return path.is_dir() and (path / "manifest.json").is_file() and (path / "content.md").is_file()

INSIGHTS_PIPELINE_KWARGS = {"skip_refine": True, "skip_enrich": True}


def _run_pipeline_to_workspace(
    input_path: Path,
    output_dir: Path,
    *,
    overwrite: bool,
    on_progress: Callable[[str, dict], None] | None = None,
) -> OutputWorkspace:
    result = run_pipeline(
        input_path,
        output_dir,
        overwrite=overwrite,
        on_progress=on_progress,
        **INSIGHTS_PIPELINE_KWARGS,
    )
    if result.status not in {"success", "partial"}:
        raise WorkspaceResolveError(f"doc_chunk pipeline failed: {result.status}")
    return OutputWorkspace.open_existing(output_dir)


def prepare_workspaces(
    paths: list[Path],
    *,
    output_dir: Path | None = None,
    overwrite: bool = False,
    on_progress: Callable[[str, dict], None] | None = None,
) -> OutputWorkspace:
    if not paths:
        raise WorkspaceResolveError("at least one path is required")

    normalized = [Path(p) for p in paths]

    if len(normalized) == 1:
        path = normalized[0]
        if _is_workspace(path):
            return OutputWorkspace.open_existing(path)
        if not path.is_file():
            raise WorkspaceResolveError(f"Path is neither workspace nor file: {path}")
        if output_dir is None:
            raise WorkspaceResolveError("output_dir is required when input is a raw document file")
        return _run_pipeline_to_workspace(path, Path(output_dir), overwrite=overwrite, on_progress=on_progress)

    if len(normalized) > 2:
        raise WorkspaceResolveError("at most two document files are supported for merge")

    if output_dir is None:
        raise WorkspaceResolveError("output_dir is required when merging document files")

    for path in normalized:
        if not path.is_file():
            raise WorkspaceResolveError(f"merge requires document files, got: {path}")

    out = Path(output_dir)
    if out.exists() and overwrite:
        shutil.rmtree(out)

    temp_dirs: list[Path] = []
    try:
        sources: list[tuple[Path, str]] = []
        for index, input_path in enumerate(normalized, start=1):
            temp = Path(tempfile.mkdtemp(prefix=f"tender_insights_ws{index}_"))
            temp_dirs.append(temp)

            def _file_progress(
                substage: str,
                payload: dict,
                *,
                file_index: int = index,
                file_name: str = input_path.name,
            ) -> None:
                if on_progress is not None:
                    on_progress(
                        substage,
                        {
                            **payload,
                            "file_index": file_index,
                            "file_total": len(normalized),
                            "file_name": file_name,
                        },
                    )

            _run_pipeline_to_workspace(
                input_path,
                temp,
                overwrite=True,
                on_progress=_file_progress,
            )
            sources.append((temp, input_path.name))

        if on_progress:
            on_progress(
                "merge",
                {
                    "message": "合并工作区",
                    "file_total": len(normalized),
                    "file_index": len(normalized),
                },
            )

        if out.exists():
            shutil.rmtree(out)
        merge_workspaces(out, sources=sources)
        validate_merged_workspace(out)
        return OutputWorkspace.open_existing(out)
    finally:
        for temp in temp_dirs:
            shutil.rmtree(temp, ignore_errors=True)
