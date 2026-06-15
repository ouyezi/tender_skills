from __future__ import annotations

from doc_chunk.models.chunk import ContentChunk
from doc_chunk.models.document_tree import DocumentTreeFile
from doc_chunk.models.linkage import LinkageEntry, LinkageFile
from doc_chunk.models.outline import OutlineTree


def build_linkage(
    outline: OutlineTree,
    document_tree: DocumentTreeFile,
    chunks: list[ContentChunk],
    *,
    outline_source: str = "original",
) -> LinkageFile:
    tree_by_outline: dict[str, list[str]] = {}
    for node in document_tree.nodes:
        if node.outline_node_id:
            tree_by_outline.setdefault(node.outline_node_id, []).append(node.node_id)

    chunks_by_outline: dict[str, list[ContentChunk]] = {}
    for chunk in chunks:
        for node_id in chunk.original_node_ids:
            chunks_by_outline.setdefault(node_id, []).append(chunk)

    entries: list[LinkageEntry] = []
    for node in outline.nodes:
        node_chunks = chunks_by_outline.get(node.node_id, [])
        if not node_chunks:
            continue
        primary = next((c for c in node_chunks if c.heading_level is not None), node_chunks[0])
        entries.append(
            LinkageEntry(
                outline_node_id=node.node_id,
                document_tree_node_ids=tree_by_outline.get(node.node_id, []),
                chunk_ids=[c.chunk_id for c in node_chunks],
                primary_chunk_id=primary.chunk_id,
            )
        )

    return LinkageFile(outline_source=outline_source, entries=entries)  # type: ignore[arg-type]
