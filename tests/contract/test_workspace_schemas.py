import json
from pathlib import Path

import pytest

from doc_chunk.models.chunk import ChunkIndex, ContentChunk
from doc_chunk.models.manifest import Manifest
from doc_chunk.models.outline import OutlineNode, OutlineTree

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "expected"


def test_manifest_minimal_fixture_parses():
    data = json.loads((FIXTURES / "manifest_minimal.json").read_text(encoding="utf-8"))
    manifest = Manifest.model_validate(data)
    assert manifest.schema_version == "1.0"
    assert manifest.status == "success"


def test_outline_node_level_validation():
    with pytest.raises(ValueError):
        OutlineNode(
            node_id="n1",
            title="bad",
            level=9,
            parent_id=None,
            sort_order=0,
        )


def test_content_chunk_defaults():
    chunk = ContentChunk(chunk_id="chunk-0001", title="Intro")
    assert chunk.section_path == []
    assert chunk.outline_source == "original"


def test_chunk_index_schema_version():
    index = ChunkIndex()
    assert index.schema_version == "1.0"


def test_outline_tree_empty():
    tree = OutlineTree(strategy="toc")
    assert tree.nodes == []
