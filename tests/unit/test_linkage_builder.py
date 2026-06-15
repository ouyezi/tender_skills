from doc_chunk.linkage.builder import build_linkage
from doc_chunk.models.chunk import ContentChunk
from doc_chunk.models.document_tree import DocumentTreeFile, DocumentTreeNode
from doc_chunk.models.outline import OutlineNode, OutlineTree


def test_linkage_maps_outline_to_chunks_and_tree() -> None:
    outline = OutlineTree(
        nodes=[
            OutlineNode(node_id="n1", title="A", level=1, parent_id=None, sort_order=0),
        ]
    )
    tree = DocumentTreeFile(
        nodes=[
            DocumentTreeNode(
                node_id="t1",
                parent_id=None,
                outline_node_id="n1",
                node_type="heading",
                title="A",
                level=1,
                sort_order=0,
                source_block_index=0,
            )
        ]
    )
    chunks = [
        ContentChunk(chunk_id="chunk-0001", title="A", original_node_ids=["n1"], heading_level=1),
        ContentChunk(chunk_id="chunk-0002", title="A", original_node_ids=["n1"], heading_level=None),
    ]
    linkage = build_linkage(outline, tree, chunks, outline_source="original")
    assert linkage.entries[0].outline_node_id == "n1"
    assert linkage.entries[0].chunk_ids == ["chunk-0001", "chunk-0002"]
    assert linkage.entries[0].primary_chunk_id == "chunk-0001"
    assert linkage.entries[0].document_tree_node_ids == ["t1"]
