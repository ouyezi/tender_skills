from __future__ import annotations

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.document_tree import DocumentTreeFile, DocumentTreeNode
from doc_chunk.models.outline import OutlineNode, OutlineTree


def _outline_by_block_start(outline: OutlineTree) -> dict[int, OutlineNode]:
    mapping: dict[int, OutlineNode] = {}
    for node in outline.nodes:
        block_start = node.anchor.block_start
        if block_start is not None:
            mapping[block_start] = node
    return mapping


def _heading_stack_parent(stack: list[DocumentTreeNode], level: int | None) -> str | None:
    if level is None:
        return stack[-1].node_id if stack else None
    while stack and stack[-1].level is not None and stack[-1].level >= level:
        stack.pop()
    return stack[-1].node_id if stack else None


def build_document_tree(
    blocks: ContentBlocksFile,
    outline: OutlineTree,
    *,
    content_md: str,
) -> DocumentTreeFile:
    outline_by_block = _outline_by_block_start(outline)
    nodes: list[DocumentTreeNode] = []
    heading_stack: list[DocumentTreeNode] = []
    heading_counter = 0
    node_counter = 0

    for block in blocks.blocks:
        outline_node = outline_by_block.get(block.block_index)
        if outline_node is not None and block.block_type in {"heading", "paragraph"}:
            heading_counter += 1
            node_id = f"t{heading_counter:04d}"
            parent_id = _heading_stack_parent(heading_stack, outline_node.level)
            tree_node = DocumentTreeNode(
                node_id=node_id,
                parent_id=parent_id,
                outline_node_id=outline_node.node_id,
                node_type="heading",
                title=outline_node.title,
                level=outline_node.level,
                sort_order=node_counter,
                source_block_index=block.block_index,
                text=None,
            )
            nodes.append(tree_node)
            heading_stack.append(tree_node)
            node_counter += 1
            continue

        node_type = block.block_type if block.block_type != "heading" else "paragraph"
        if node_type == "heading":
            node_type = "paragraph"

        text = None
        image_ref = block.image_ref
        if node_type in {"paragraph", "table"}:
            text = content_md[block.char_start : block.char_end].strip() or block.text_preview
        parent_id = heading_stack[-1].node_id if heading_stack else None
        node_counter += 1
        nodes.append(
            DocumentTreeNode(
                node_id=f"t{node_counter:04d}",
                parent_id=parent_id,
                outline_node_id=None,
                node_type=node_type,  # type: ignore[arg-type]
                title=None,
                level=None,
                sort_order=node_counter - 1,
                source_block_index=block.block_index,
                text=text,
                image_ref=image_ref,
            )
        )

    return DocumentTreeFile(nodes=nodes)
