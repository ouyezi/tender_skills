from __future__ import annotations

from pathlib import Path

from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.table.placeholders import format_table_ref_comment
from doc_chunk.workspace.layout import OutputWorkspace


class BlockAccumulator:
    def __init__(self) -> None:
        self._markdown_parts: list[str] = []
        self._blocks: list[ContentBlockRecord] = []
        self._cursor = 0

    def _append(self, text: str, block_type: str, *, image_ref: str | None = None) -> None:
        if not text and block_type != "image":
            return
        start = self._cursor
        self._markdown_parts.append(text)
        self._cursor += len(text)
        preview = None if block_type == "image" else (text[:120] or None)
        self._blocks.append(
            ContentBlockRecord(
                block_index=len(self._blocks),
                block_type=block_type,  # type: ignore[arg-type]
                char_start=start,
                char_end=self._cursor,
                text_preview=preview,
                image_ref=image_ref,
            )
        )

    def add_paragraph(self, text: str) -> None:
        self._append(f"{text}\n\n", "paragraph")

    def add_heading(self, level: int, text: str) -> None:
        depth = max(1, min(6, level))
        self._append(f"{'#' * depth} {text.strip()}\n\n", "heading")

    def add_table(self, table_md: str, *, table_ref: str | None = None) -> None:
        start = self._cursor
        body = f"{table_md}\n\n"
        if table_ref:
            body = f"{format_table_ref_comment(table_ref)}\n{body}"
        self._markdown_parts.append(body)
        self._cursor += len(body)
        preview = table_md[:120] or None
        self._blocks.append(
            ContentBlockRecord(
                block_index=len(self._blocks),
                block_type="table",
                char_start=start,
                char_end=self._cursor,
                text_preview=preview,
                table_ref=table_ref,
            )
        )

    def add_image(self, image_ref: str, alt: str = "image") -> None:
        line = f"![{alt}]({image_ref})\n\n"
        self._append(line, "image", image_ref=image_ref)

    @property
    def markdown(self) -> str:
        return "".join(self._markdown_parts)

    @property
    def block_count(self) -> int:
        return len(self._blocks)

    def finalize(self) -> ContentBlocksFile:
        return ContentBlocksFile(schema_version="1.1", blocks=list(self._blocks))


def write_content_blocks(workspace: OutputWorkspace, blocks_file: ContentBlocksFile) -> Path:
    path = workspace.content_blocks_path
    path.write_text(blocks_file.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_accumulator_markdown(workspace: OutputWorkspace, acc: BlockAccumulator) -> Path:
    rendered = acc.markdown.rstrip()
    workspace.content_path.write_text(f"{rendered}\n" if rendered else "", encoding="utf-8")
    return workspace.content_path
