from __future__ import annotations

from doc_chunk.chunk.refined_planner import plan_chunks_from_refined
from doc_chunk.models.outline import Anchor, OutlineMappingFile, OutlineNode, OutlineTree


def test_refined_planner_uses_mapping_ranges() -> None:
    content = "# 第一章\n正文A\n# 第二章\n正文B\n"
    refined = OutlineTree(
        strategy="heading_heuristic",
        nodes=[
            OutlineNode(
                node_id="r1",
                title="合并章节",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
                source_refs=["n1", "n2"],
            )
        ],
    )
    mapping = OutlineMappingFile.model_validate(
        {
            "mappings": [
                {
                    "refined_node_id": "r1",
                    "source_node_ids": ["n1", "n2"],
                    "markdown_range": {"char_start": 0, "char_end": len(content)},
                    "operation": "merge",
                }
            ]
        }
    )

    chunks = plan_chunks_from_refined(content, refined, mapping, max_tokens=20000)
    assert len(chunks) == 1
    assert chunks[0].outline_source == "refined"
    assert chunks[0].refined_node_id == "r1"
    assert chunks[0].original_node_ids == ["n1", "n2"]
