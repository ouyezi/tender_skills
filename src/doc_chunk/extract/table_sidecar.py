from __future__ import annotations

from doc_chunk.models.table_model import TableSidecar, TablesIndex, TablesIndexEntry
from doc_chunk.workspace.layout import OutputWorkspace


class TableSidecarWriter:
    def __init__(self, workspace: OutputWorkspace) -> None:
        self._ws = workspace
        self._ws.tables_dir.mkdir(parents=True, exist_ok=True)
        self._entries: list[TablesIndexEntry] = []

    def write(self, sidecar: TableSidecar) -> str:
        rel = f"tables/t{sidecar.block_index:04d}.json"
        path = self._ws.root / rel
        path.write_text(sidecar.model_dump_json(indent=2), encoding="utf-8")
        self._entries.append(TablesIndexEntry(block_index=sidecar.block_index, path=rel))
        return rel

    def finalize(self) -> None:
        index = TablesIndex(tables=sorted(self._entries, key=lambda e: e.block_index))
        self._ws.tables_index_path.write_text(index.model_dump_json(indent=2), encoding="utf-8")
