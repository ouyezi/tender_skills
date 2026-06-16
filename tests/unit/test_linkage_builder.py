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
                node_id="t0001",
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
    assert linkage.entries[0].document_tree_node_ids == ["t0001"]


def test_linkage_entry_for_outline_without_chunk() -> None:
    outline = OutlineTree(
        nodes=[
            OutlineNode(node_id="n1", title="A", level=1, parent_id=None, sort_order=0),
            OutlineNode(node_id="n2", title="B", level=1, parent_id=None, sort_order=1),
        ]
    )
    tree = DocumentTreeFile(
        nodes=[
            DocumentTreeNode(
                node_id="t0001", parent_id=None, outline_node_id="n1",
                node_type="heading", title="A", level=1, sort_order=0, source_block_index=0,
            ),
            DocumentTreeNode(
                node_id="t0002", parent_id=None, outline_node_id="n2",
                node_type="heading", title="B", level=1, sort_order=1, source_block_index=1,
            ),
        ]
    )
    chunks = [
        ContentChunk(chunk_id="chunk-0001", title="A", original_node_ids=["n1"], heading_level=1),
    ]
    linkage = build_linkage(outline, tree, chunks, outline_source="original")
    assert len(linkage.entries) == 2
    n2 = next(e for e in linkage.entries if e.outline_node_id == "n2")
    assert n2.chunk_ids == []
    assert n2.primary_chunk_id is None
    assert n2.document_tree_node_ids == ["t0002"]


def test_linkage_collects_missing_tree_warnings() -> None:
    outline = OutlineTree(
        strategy="toc",
        nodes=[OutlineNode(node_id="n1", title="A", level=1, parent_id=None, sort_order=0)],
    )
    tree = DocumentTreeFile(nodes=[])
    linkage, warnings = build_linkage(outline, tree, [], outline_source="original", collect_warnings=True)
    assert linkage.entries[0].document_tree_node_ids == []
    assert any("linkage_missing_tree_node:n1" in w for w in warnings)
