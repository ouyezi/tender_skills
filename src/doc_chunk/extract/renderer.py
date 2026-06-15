from __future__ import annotations

from pathlib import Path

from doc_chunk.workspace.layout import OutputWorkspace


def heading_line(level: int, text: str) -> str:
    depth = max(1, min(6, level))
    return f"{'#' * depth} {text.strip()}"


def paragraph_line(text: str) -> str:
    return text.strip()


def image_line(alt_text: str, rel_path: str) -> str:
    return f"![{alt_text}]({rel_path})"


def write_content_markdown(workspace: OutputWorkspace, lines: list[str]) -> Path:
    rendered = "\n\n".join(line for line in lines if line.strip()).strip()
    workspace.content_path.write_text(f"{rendered}\n" if rendered else "", encoding="utf-8")
    return workspace.content_path
