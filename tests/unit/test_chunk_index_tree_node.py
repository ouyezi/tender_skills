from doc_chunk.api import _populate_chunk_index_tree_nodes
from doc_chunk.models.chunk import ChunkIndex, ChunkIndexEntry
from doc_chunk.models.linkage import LinkageEntry, LinkageFile


def test_populate_document_tree_node_id_from_linkage() -> None:
    index = ChunkIndex(
        chunks=[
            ChunkIndexEntry(
                chunk_id="chunk-0001",
                title="A",
                heading_level=1,
                original_node_ids=["n1"],
                path="chunk-0001.json",
            ),
        ]
    )
    linkage = LinkageFile(
        entries=[
            LinkageEntry(outline_node_id="n1", document_tree_node_ids=["t0003"], chunk_ids=["chunk-0001"]),
        ]
    )
    warnings = _populate_chunk_index_tree_nodes(index, linkage)
    assert index.chunks[0].document_tree_node_id == "t0003"
    assert warnings == []


def test_populate_emits_mismatch_warning() -> None:
    index = ChunkIndex(
        chunks=[
            ChunkIndexEntry(
                chunk_id="chunk-0001",
                title="A",
                heading_level=1,
                original_node_ids=["n1"],
                path="chunk-0001.json",
                document_tree_node_id="t0001",
            ),
        ]
    )
    linkage = LinkageFile(
        entries=[
            LinkageEntry(outline_node_id="n1", document_tree_node_ids=["t0003"], chunk_ids=["chunk-0001"]),
        ]
    )
    warnings = _populate_chunk_index_tree_nodes(index, linkage)
    assert warnings == ["chunk_tree_node_mismatch:chunk-0001"]
    assert index.chunks[0].document_tree_node_id == "t0003"
