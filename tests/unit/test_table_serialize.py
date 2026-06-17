from doc_chunk.extract.table_serialize import (
    logical_to_llm_fallback,
    logical_to_markdown,
    records_to_llm_text,
)


def test_logical_to_markdown() -> None:
    md = logical_to_markdown([["姓名", "角色"], ["刘敏", "开发"]])
    assert "| 姓名 | 角色 |" in md
    assert "| 刘敏 | 开发 |" in md
    assert "姓名 | 姓名" not in md


def test_logical_to_markdown_empty() -> None:
    assert logical_to_markdown([]) == ""


def test_records_to_llm_text_personnel() -> None:
    records = [{"姓名": "刘敏", "级别": "高级Java工程师"}]
    text = records_to_llm_text("personnel_dual_row", records, logical_rows=[])
    assert "【表格:人员信息】" in text
    assert "姓名: 刘敏" in text
    assert "级别: 高级Java工程师" in text


def test_records_to_llm_text_simple() -> None:
    records = [{"a": "1", "b": "2"}]
    text = records_to_llm_text("simple", records, logical_rows=[])
    assert "【表格:列表】" in text
    assert "--- 行 1 ---" in text
    assert "a: 1" in text


def test_records_to_llm_text_key_value() -> None:
    records = [{"项目名": "招标", "预算": "100万"}]
    text = records_to_llm_text("key_value", records, logical_rows=[])
    assert "【表格:键值】" in text
    assert "项目名: 招标" in text


def test_records_to_llm_text_fallback() -> None:
    logical_rows = [["a", "b"], ["1", "2"]]
    text = records_to_llm_text("fallback", [], logical_rows=logical_rows)
    assert text == logical_to_llm_fallback(logical_rows)
    assert "【表格:原始】" in text
