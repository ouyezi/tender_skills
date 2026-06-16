from __future__ import annotations

from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.document_tree import DocumentTreeFile, DocumentTreeNode
from doc_chunk.models.outline import OutlineNode, OutlineTree


def is_flat_fallback_exempt(outline: OutlineTree) -> bool:
    return outline.strategy == "flat_fallback" and len(outline.nodes) == 1


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


def _duplicate_anchor_warnings(outline: OutlineTree) -> list[str]:
    counts: dict[int, int] = {}
    for node in outline.nodes:
        block_start = node.anchor.block_start
        if block_start is not None:
            counts[block_start] = counts.get(block_start, 0) + 1
    return [f"outline_duplicate_anchor:{block_start}" for block_start, count in counts.items() if count > 1]


def _insert_index_for_synth_heading(nodes: list[DocumentTreeNode], block_idx: int) -> int:
    last_heading_at_block = -1
    for i, node in enumerate(nodes):
        if node.source_block_index == block_idx and node.node_type == "heading":
            last_heading_at_block = i
    if last_heading_at_block >= 0:
        return last_heading_at_block + 1
    for i, node in enumerate(nodes):
        if node.source_block_index == block_idx and node.node_type != "heading":
            return i
    return len(nodes)


def _synthesize_missing_headings(
    outline: OutlineTree,
    nodes: list[DocumentTreeNode],
    *,
    node_counter: int,
) -> tuple[list[DocumentTreeNode], int]:
    if is_flat_fallback_exempt(outline):
        return nodes, node_counter

    heading_by_outline = {
        node.outline_node_id: node.node_id
        for node in nodes
        if node.node_type == "heading" and node.outline_node_id
    }
    missing = sorted(
        [node for node in outline.nodes if node.node_id not in heading_by_outline],
        key=lambda node: node.sort_order,
    )

    for outline_node in missing:
        block_idx = outline_node.anchor.block_start if outline_node.anchor.block_start is not None else 0
        parent_id = None
        if outline_node.parent_id:
            parent_id = heading_by_outline.get(outline_node.parent_id)

        node_counter += 1
        new_heading = DocumentTreeNode(
            node_id=f"t{node_counter:04d}",
            parent_id=parent_id,
            outline_node_id=outline_node.node_id,
            node_type="heading",
            title=outline_node.title,
            level=outline_node.level,
            sort_order=0,
            source_block_index=block_idx,
            text=None,
        )
        insert_at = _insert_index_for_synth_heading(nodes, block_idx)
        nodes.insert(insert_at, new_heading)
        heading_by_outline[outline_node.node_id] = new_heading.node_id

    nodes = [node.model_copy(update={"sort_order": index}) for index, node in enumerate(nodes)]
    return nodes, node_counter


def build_document_tree(
    blocks: ContentBlocksFile,
    outline: OutlineTree,
    *,
    content_md: str,
) -> DocumentTreeFile:
    tree, _warnings = build_document_tree_with_warnings(blocks, outline, content_md=content_md)
    return tree


def build_document_tree_with_warnings(
    blocks: ContentBlocksFile,
    outline: OutlineTree,
    *,
    content_md: str,
) -> tuple[DocumentTreeFile, list[str]]:
    outline_by_block = _outline_by_block_start(outline)
    nodes: list[DocumentTreeNode] = []
    heading_stack: list[DocumentTreeNode] = []
    node_counter = 0

    for block in blocks.blocks:
        outline_node = outline_by_block.get(block.block_index)
        if outline_node is not None and block.block_type in {"heading", "paragraph"}:
            node_counter += 1
            node_id = f"t{node_counter:04d}"
            parent_id = _heading_stack_parent(heading_stack, outline_node.level)
            tree_node = DocumentTreeNode(
                node_id=node_id,
                parent_id=parent_id,
                outline_node_id=outline_node.node_id,
                node_type="heading",
                title=outline_node.title,
                level=outline_node.level,
                sort_order=node_counter - 1,
                source_block_index=block.block_index,
                text=None,
            )
            nodes.append(tree_node)
            heading_stack.append(tree_node)
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

    nodes, node_counter = _synthesize_missing_headings(outline, nodes, node_counter=node_counter)
    warnings = _duplicate_anchor_warnings(outline)
    return DocumentTreeFile(nodes=nodes), warnings
