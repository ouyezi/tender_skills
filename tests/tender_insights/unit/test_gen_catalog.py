from __future__ import annotations

from pathlib import Path

import pytest
from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.gen_catalog.accept import accept_gen_catalog_draft
from tender_insights.gen_catalog.excerpt import pick_node_excerpt
from tender_insights.gen_catalog.extractor import gen_catalog_workspace, run_gen_catalog_initial
from tender_insights.gen_catalog.models import BidOutlineNode
from tender_insights.gen_catalog.prerequisites import validate_prerequisites
from tender_insights.gen_catalog.queue import build_node_queue, find_node, next_pending_node_id
from tender_insights.gen_catalog.render import render_bid_outline_markdown
from tender_insights.gen_catalog.session import clear_gen_catalog_artifacts, load_session, save_session
from tender_insights.gen_catalog.models import GenCatalogSession
from tender_insights.gen_catalog.prompts import GEN_CATALOG_INITIAL_SYSTEM, GEN_CATALOG_REFINE_SYSTEM
from tender_insights.gen_catalog.context import build_initial_user_prompt
from tender_insights.interpret.models import (
    DirectoryOutline,
    DirectoryOutlineNode,
    DirectoryRequirement,
    InterpretationFile,
    InterpretationOverview,
)
from tests.helpers.gen_catalog_fake_llm import GenCatalogFakeLLM


def _node(node_id: str, title: str, children: list | None = None) -> BidOutlineNode:
    return BidOutlineNode(
        id=node_id,
        title=title,
        level=1,
        order=1,
        children=children or [],
    )


def _minimal_interpretation(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "content.md").write_text("# 正文\n", encoding="utf-8")
    (ws / "manifest.json").write_text(
        '{"schema_version":"1.0","status":"success","source":{"path":"/tmp/a.docx","file_name":"a.docx","file_type":"docx"},"stages":{},"outputs":{},"warnings":[],"errors":[]}',
        encoding="utf-8",
    )
    data = InterpretationFile(
        source_workspace=str(ws),
        overview=InterpretationOverview(
            summary="s",
            disqualification_summary="d",
            scoring_summary="sc",
            bid_risk_summary="b",
            directory_summary="dir",
        ),
        directory_requirements=[
            DirectoryRequirement(
                id="dr-001",
                title="文件组成",
                required_sections=["投标函"],
                mandatory=True,
                source_excerpt="组成",
                section_path=["格式"],
                confidence=0.9,
            )
        ],
        directory_outline=DirectoryOutline(
            nodes=[DirectoryOutlineNode(id="dir-001", title="投标函", level=1, order=1)]
        ),
    )
    path = ws / "interpretation.json"
    path.write_text(data.model_dump_json(), encoding="utf-8")
    (ws / "interpret").mkdir(parents=True)
    (ws / "interpret" / "source_content.md").write_text("# 技术方案\n\n正文\n", encoding="utf-8")
    return ws


def _open_ws(path: Path) -> OutputWorkspace:
    return OutputWorkspace.open_existing(path)


def test_build_node_queue_preorder() -> None:
    root = BidOutlineNode(
        id="bid-root",
        title="root",
        level=0,
        order=0,
        children=[
            _node("bid-001", "A", [_node("bid-002", "A1")]),
            _node("bid-003", "B"),
        ],
    )
    assert build_node_queue(root) == ["bid-001", "bid-002", "bid-003"]


def test_next_pending_node_id_skips_completed() -> None:
    queue = ["bid-001", "bid-002", "bid-003"]
    completed = ["initial", "bid-001"]
    assert next_pending_node_id(queue, completed) == "bid-002"


def test_find_node_returns_subtree() -> None:
    child = _node("bid-002", "child")
    root = BidOutlineNode(id="bid-root", title="root", level=0, order=0, children=[child])
    found = find_node(root, "bid-002")
    assert found is not None
    assert found.title == "child"


def test_pick_node_excerpt_respects_max_chars() -> None:
    text = "a" * 3000
    excerpt = pick_node_excerpt(text, node_title="技术方案", max_chars=2000)
    assert len(excerpt) <= 2000


def test_pick_node_excerpt_merges_short_tail() -> None:
    text = "短段\n\n" + ("b" * 500)
    excerpt = pick_node_excerpt(text, node_title="短段", max_chars=2000, min_chars=200)
    assert "bbbb" in excerpt
    assert len(excerpt) >= 200


def test_validate_prerequisites_requires_interpretation(tmp_path: Path) -> None:
    ws_root = tmp_path / "empty"
    ws_root.mkdir()
    (ws_root / "content.md").write_text("# x\n", encoding="utf-8")
    (ws_root / "manifest.json").write_text(
        '{"schema_version":"1.0","status":"success","source":{"path":"/tmp/a.docx","file_name":"a.docx","file_type":"docx"},"stages":{},"outputs":{},"warnings":[],"errors":[]}',
        encoding="utf-8",
    )
    ws = _open_ws(ws_root)
    with pytest.raises(FileNotFoundError):
        validate_prerequisites(ws)


def test_validate_prerequisites_warns_missing_brief(tmp_path: Path) -> None:
    ws_root = _minimal_interpretation(tmp_path)
    report = validate_prerequisites(_open_ws(ws_root))
    assert report.warnings


def test_session_roundtrip(tmp_path: Path) -> None:
    ws = _open_ws(_minimal_interpretation(tmp_path))
    session = GenCatalogSession(mode="step", status="paused", step_index=1, step_total=3)
    save_session(ws, session)
    loaded = load_session(ws)
    assert loaded.step_index == 1
    clear_gen_catalog_artifacts(ws)
    assert not (ws.root / "gen_catalog" / "session.json").exists()


def test_prompts_are_static() -> None:
    assert "JSON" in GEN_CATALOG_INITIAL_SYSTEM
    assert "完整" in GEN_CATALOG_REFINE_SYSTEM


def test_build_initial_user_prompt_includes_overview(tmp_path: Path) -> None:
    ws_root = _minimal_interpretation(tmp_path)
    report = validate_prerequisites(_open_ws(ws_root))
    user = build_initial_user_prompt(report)
    assert "解读概要" in user


def test_run_gen_catalog_initial_writes_draft(tmp_path: Path) -> None:
    ws = _open_ws(_minimal_interpretation(tmp_path))
    client = GenCatalogFakeLLM()
    report = validate_prerequisites(ws)
    draft = run_gen_catalog_initial(ws, client, report=report)
    assert draft.root.id == "bid-root"
    assert (ws.root / "bid_outline.draft.json").is_file()


def test_gen_catalog_workspace_step_pauses_after_initial(tmp_path: Path) -> None:
    ws = _open_ws(_minimal_interpretation(tmp_path))
    client = GenCatalogFakeLLM()
    result = gen_catalog_workspace(ws, client, mode="step", run_limit=1)
    assert result.status == "paused"
    session = load_session(ws)
    assert "initial" in session.completed_steps


def test_gen_catalog_workspace_auto_completes(tmp_path: Path) -> None:
    ws = _open_ws(_minimal_interpretation(tmp_path))
    client = GenCatalogFakeLLM()
    result = gen_catalog_workspace(ws, client, mode="auto")
    assert result.status == "awaiting_accept"


def test_accept_writes_final_artifacts(tmp_path: Path) -> None:
    ws = _open_ws(_minimal_interpretation(tmp_path))
    client = GenCatalogFakeLLM()
    gen_catalog_workspace(ws, client, mode="auto")
    accept_gen_catalog_draft(ws)
    assert (ws.root / "bid_outline.json").is_file()
    assert (ws.root / "bid_outline.md").is_file()
    text = (ws.root / "bid_outline.md").read_text(encoding="utf-8")
    assert "投标函" in text


def test_render_bid_outline_markdown() -> None:
    from tender_insights.gen_catalog.models import BidOutlineFile

    draft = BidOutlineFile(
        source_workspace="/tmp",
        interpretation_schema="1.2",
        mode="auto",
        status="awaiting_accept",
        overview_snapshot={"summary": "x"},
        root=BidOutlineNode(
            id="bid-root",
            title="投标文件",
            level=0,
            order=0,
            children=[
                BidOutlineNode(
                    id="bid-001",
                    title="投标函",
                    level=1,
                    order=1,
                    summary="概要",
                    writing_spec="规范",
                )
            ],
        ),
    )
    md = render_bid_outline_markdown(draft)
    assert "投标函" in md
