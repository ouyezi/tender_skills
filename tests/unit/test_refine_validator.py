from __future__ import annotations

from doc_chunk.models.outline import Anchor, OutlineMappingFile, OutlineNode, OutlineTree
from doc_chunk.outline_refine.validator import OutlineMappingValidator


def _original_outline() -> OutlineTree:
    return OutlineTree(
        strategy="heading_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="第一章",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
            ),
            OutlineNode(
                node_id="n2",
                title="第二章",
                level=1,
                parent_id=None,
                sort_order=1,
                anchor=Anchor(block_index=1),
            ),
        ],
    )


def _refined_outline() -> OutlineTree:
    return OutlineTree(
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
            ),
        ],
    )


def test_validator_passes_for_valid_mapping() -> None:
    mapping = OutlineMappingFile.model_validate(
        {
            "mappings": [
                {
                    "refined_node_id": "r1",
                    "source_node_ids": ["n1", "n2"],
                    "markdown_range": {"char_start": 0, "char_end": 20},
                    "operation": "merge",
                }
            ]
        }
    )
    result = OutlineMappingValidator(strict=True).validate(
        original_outline=_original_outline(),
        refined_outline=_refined_outline(),
        mapping=mapping,
    )
    assert result.passed is True


def test_validator_fails_on_unknown_source_node() -> None:
    mapping = OutlineMappingFile.model_validate(
        {
            "mappings": [
                {
                    "refined_node_id": "r1",
                    "source_node_ids": ["n404"],
                    "markdown_range": {"char_start": 0, "char_end": 20},
                    "operation": "merge",
                }
            ]
        }
    )
    result = OutlineMappingValidator(strict=True).validate(
        original_outline=_original_outline(),
        refined_outline=_refined_outline(),
        mapping=mapping,
    )
    assert result.passed is False
    assert any("unknown source node ids" in err for err in result.errors)
