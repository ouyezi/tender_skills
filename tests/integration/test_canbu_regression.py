from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

import pytest

from doc_chunk.api import run_pipeline

CANBU = os.environ.get("DOC_CHUNK_CANBU_FIXTURE")
T_BASE = os.environ.get("DOC_CHUNK_CANBU_T_BASE")


@pytest.mark.skipif(not CANBU, reason="set DOC_CHUNK_CANBU_FIXTURE to run canbu regression")
def test_canbu_document_tree_and_linkage_invariants(tmp_path: Path) -> None:
    src = Path(CANBU)
    ws = tmp_path / "canbu"
    run_pipeline(src, ws, overwrite=True, skip_enrich=True)
    outline = json.loads((ws / "outline.json").read_text(encoding="utf-8"))["nodes"]
    tree = json.loads((ws / "document_tree.json").read_text(encoding="utf-8"))["nodes"]
    linkage = json.loads((ws / "linkage.json").read_text(encoding="utf-8"))["entries"]
    index = json.loads((ws / "chunks" / "index.json").read_text(encoding="utf-8"))["chunks"]

    ids = [node["node_id"] for node in tree]
    assert len(ids) == len(set(ids))
    heading_outline = {
        node["outline_node_id"]
        for node in tree
        if node["node_type"] == "heading" and node.get("outline_node_id")
    }
    assert heading_outline == {node["node_id"] for node in outline}
    assert len(linkage) == len(outline)
    assert all(entry["document_tree_node_ids"] for entry in linkage)

    main_chunks = [entry for entry in index if entry.get("heading_level") is not None]
    ratio = len(main_chunks) / max(len(outline), 1)
    assert 0.8 <= ratio <= 1.2


@pytest.mark.skipif(not CANBU or not T_BASE, reason="needs DOC_CHUNK_CANBU_FIXTURE and DOC_CHUNK_CANBU_T_BASE")
def test_canbu_pipeline_wall_time_within_budget(tmp_path: Path) -> None:
    src = Path(CANBU)
    times: list[float] = []
    for i in range(3):
        ws = tmp_path / f"canbu-{i}"
        start = time.perf_counter()
        run_pipeline(src, ws, overwrite=True, skip_enrich=True)
        times.append(time.perf_counter() - start)
    t_003 = statistics.median(times)
    t_base = float(T_BASE)
    ratio = t_003 / t_base
    print(f"NF1 canbu timing: T_base={t_base:.1f}s T_003={t_003:.1f}s ratio={ratio:.2f}")
    assert t_003 <= 1.2 * t_base
