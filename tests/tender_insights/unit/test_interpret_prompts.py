from tender_insights.interpret.prompts import build_segment_appendix, build_segment_prompt


def test_build_segment_appendix_for_respondent_notice() -> None:
    appendix = build_segment_appendix(["第二章 响应人须知", "评审办法"])
    assert "scoring_items" in appendix
    assert "children" in appendix


def test_build_segment_appendix_empty_when_no_keywords() -> None:
    assert build_segment_appendix(["第一章 总则"]) == ""


def test_build_segment_prompt_includes_appendix() -> None:
    prompt = build_segment_prompt("seg-001", ["第二章 响应人须知"], "正文内容")
    assert "正文内容" in prompt
    assert "scoring_items" in prompt


def test_build_segment_prompt_mixed_format_and_scoring_table() -> None:
    md = "【表格: 评标表】\n评分说明 | 分值\n商品方案 | 0-2分\n\n一、投标函\n"
    prompt = build_segment_prompt(
        "seg-024",
        ["第六章 响应文件格式"],
        md,
    )
    assert "directory_requirements" in prompt
    assert "scoring_items" in prompt
    assert "禁止只提取目录" in prompt


def test_build_segment_prompt_scoring_table_segment() -> None:
    md = "【表格: 评标表】\n评分说明 | 分值\n商品方案 | 0-2分"
    prompt = build_segment_prompt("seg-scoring-001", ["第三章 评审办法"], md)
    assert "directory_requirements 返回 []" in prompt
    assert "完整提取全部 scoring_items" in prompt
