from doc_chunk.models.content_block import ContentBlockRecord, ContentBlocksFile
from doc_chunk.models.table_model import TableSidecar
from doc_chunk.table.access import load_table_model, substitute_tables_for_llm
from doc_chunk.workspace.layout import OutputWorkspace


def test_substitute_tables_for_llm_replaces_markdown(tmp_path):
    ws = OutputWorkspace.create(tmp_path / "ws", overwrite=False)
    md_table = "| 姓名 | 角色 |\n| --- | --- |\n| 刘敏 | 开发 |"
    llm = "【表格:人员信息】\n姓名: 刘敏"
    content = f"前文\n\n{md_table}\n\n后文"
    ws.content_path.write_text(content, encoding="utf-8")
    start = content.index("|")
    end = content.index("后文")
    sidecar = TableSidecar(
        block_index=0,
        layout_type="simple",
        grid_width=2,
        grid={"rows": []},
        logical_rows=[],
        markdown=md_table,
        llm_text=llm,
    )
    (ws.tables_dir).mkdir(exist_ok=True)
    (ws.tables_dir / "t0000.json").write_text(sidecar.model_dump_json(), encoding="utf-8")
    blocks = ContentBlocksFile(
        schema_version="1.1",
        blocks=[
            ContentBlockRecord(
                block_index=0,
                block_type="table",
                char_start=start,
                char_end=end,
                table_ref="tables/t0000.json",
            )
        ],
    )
    out = substitute_tables_for_llm(content, blocks, workspace=ws)
    assert llm in out
    assert "| 姓名 |" not in out
    assert "前文" in out and "后文" in out
