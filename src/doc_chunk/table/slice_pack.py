from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.table import Table as DocxTable

from doc_chunk.table.slice_graft import (
    graft_style_blobs,
    remap_embed_relationships,
    replace_body_with_table,
)


def build_mini_docx_for_table(source_table: DocxTable, dest_path: Path) -> None:
    source_doc = source_table._parent
    tbl_copy = deepcopy(source_table._tbl)

    dest_doc = Document()
    replace_body_with_table(dest_doc, tbl_copy)
    graft_style_blobs(source_doc, dest_doc)
    remap_embed_relationships(source_doc.part, dest_doc.part, tbl_copy)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_doc.save(dest_path)
