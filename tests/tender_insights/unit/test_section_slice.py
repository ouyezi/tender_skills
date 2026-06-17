from doc_chunk.api import extract_file, extract_outline
from doc_chunk.llm.client import FakeLLMClient
from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.section_slice import load_content_blocks, slice_for_llm
from tender_insights.interpret.extractor import interpret_workspace


def test_slice_for_llm_replaces_table_in_node_range(personnel_dual_row_docx, tmp_path) -> None:
    ws_path = tmp_path / "ws"
    extract_file(personnel_dual_row_docx, ws_path, overwrite=True)
    workspace = OutputWorkspace.open_existing(ws_path)
    content_md = workspace.content_path.read_text(encoding="utf-8")
    blocks = load_content_blocks(workspace)
    assert blocks is not None

    table_block = next(b for b in blocks.blocks if b.block_type == "table")
    start = max(0, table_block.char_start - 5)
    end = min(len(content_md), table_block.char_end + 5)
    sliced = slice_for_llm(workspace, content_md, start, end, blocks=blocks)

    assert "【表格:" in sliced
    assert "姓名: 刘敏" in sliced
    assert "| 姓名 | 姓名 |" not in sliced


def test_interpret_workspace_uses_llm_table_text(personnel_dual_row_docx, tmp_path) -> None:
    ws_path = tmp_path / "ws"
    extract_file(personnel_dual_row_docx, ws_path, overwrite=True)
    extract_outline(ws_path)
    workspace = OutputWorkspace.open_existing(ws_path)

    outline = OutlineTree(
        nodes=[
            OutlineNode(
                node_id="n1",
                title="投标人须知",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=0),
                needs_review=False,
            )
        ]
    )
    workspace.outline_path.write_text(outline.model_dump_json(indent=2), encoding="utf-8")

    client = FakeLLMClient(
        default_response=(
            '{"disqualification_items":[],"scoring_items":[],"bid_risk_items":[],"directory_requirements":[]}'
        )
    )
    interpret_workspace(workspace, client)

    assert client.calls
    user_contents = [
        str(message["content"])
        for call in client.calls
        for message in call["messages"]
        if message.get("role") == "user"
    ]
    assert any("【表格:人员信息】" in text and "姓名: 刘敏" in text for text in user_contents)
