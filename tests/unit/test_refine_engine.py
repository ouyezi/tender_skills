from __future__ import annotations

from pathlib import Path

import pytest

from doc_chunk.errors import ValidationError
from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.outline_refine.engine import OutlineRefineEngine
from doc_chunk.outline_refine.session import RefineSession


def _session(tmp_path: Path) -> RefineSession:
    original = OutlineTree(
        strategy="heading_heuristic",
        nodes=[
            OutlineNode(
                node_id="n1",
                title="第一章",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(block_index=0),
            )
        ],
    )
    return RefineSession(workspace=tmp_path / "ws", original_outline=original)


def test_refine_engine_runs_with_fake_llm(tmp_path: Path) -> None:
    llm = FakeLLMClient(
        responses=[
            (
                '{"outline_refined":{"schema_version":"1.0","strategy":"heading_heuristic","nodes":[{"node_id":"r1",'
                '"title":"合并章节","level":1,"parent_id":null,"sort_order":0,"anchor":{"block_index":0},"needs_review":false,'
                '"source_refs":["n1"]}],"derived_from":null,"accepted_at":null},'
                '"node_mappings":[{"refined_node_id":"r1","source_node_ids":["n1"],"markdown_range":{"char_start":0,"char_end":10},"operation":"rename"}],'
                '"change_summary":"重命名第一章"}'
            )
        ]
    )
    engine = OutlineRefineEngine(llm_client=llm, strict=True, max_retries=2)
    refined, mapping, summary, preview = engine.run_round(session=_session(tmp_path), instruction="重命名")
    assert refined.nodes[0].title == "合并章节"
    assert mapping.mappings[0].refined_node_id == "r1"
    assert summary == "重命名第一章"
    assert preview.validation_passed is True


def test_refine_engine_retries_and_fails_after_max(tmp_path: Path) -> None:
    llm = FakeLLMClient(responses=["not-json", "still-not-json", "again"])
    engine = OutlineRefineEngine(llm_client=llm, strict=True, max_retries=2)
    with pytest.raises(ValidationError):
        engine.run_round(session=_session(tmp_path), instruction="重命名")
    assert len(llm.calls) == 3
