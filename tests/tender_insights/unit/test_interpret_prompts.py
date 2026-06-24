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
