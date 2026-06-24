from tender_insights.interpret.models import InterpretationLLMResponse
from tender_insights.interpret.response_normalize import normalize_interpretation_llm_data


def test_normalize_coerces_directory_structure_dict() -> None:
    data = {
        "disqualification_items": [],
        "scoring_items": [],
        "bid_risk_items": [],
        "directory_requirements": [
            {
                "id": "dr-001",
                "title": "投标文件组成",
                "required_sections": [],
                "mandatory": True,
                "inferred": False,
                "structure": {
                    "纸质文件": {
                        "正本": "须与电子文件正本内容一致",
                    }
                },
                "source_excerpt": "原文",
                "section_path": ["第六章"],
                "confidence": 0.9,
            }
        ],
    }
    normalized = normalize_interpretation_llm_data(data)
    parsed = InterpretationLLMResponse.model_validate(normalized)
    assert len(parsed.directory_requirements) == 1
    structure = parsed.directory_requirements[0].structure
    assert structure[0].title == "纸质文件"
    assert structure[0].children[0].title == "正本"


def test_normalize_leaves_list_structure_unchanged() -> None:
    data = {
        "disqualification_items": [],
        "scoring_items": [],
        "bid_risk_items": [],
        "directory_requirements": [
            {
                "id": "dr-001",
                "title": "组成",
                "required_sections": [],
                "mandatory": True,
                "structure": [{"order": 1, "title": "投标函", "mandatory": True, "children": []}],
                "source_excerpt": "x",
                "section_path": [],
                "confidence": 0.8,
            }
        ],
    }
    normalized = normalize_interpretation_llm_data(data)
    parsed = InterpretationLLMResponse.model_validate(normalized)
    assert parsed.directory_requirements[0].structure[0].title == "投标函"


def test_normalize_coerces_confidence_labels_and_missing_scoring_fields() -> None:
    data = {
        "disqualification_items": [
            {
                "id": "dq-001",
                "title": "废标1",
                "summary": "摘要",
                "trigger_condition": "条件",
                "source_excerpt": "原文",
                "section_path": [],
                "confidence": "high",
            }
        ],
        "scoring_items": [
            {
                "id": "score-main-001",
                "title": "综合评分",
                "max_score": 100,
                "weight": 1.0,
                "criteria": "按细则评分",
                "children": [],
            }
        ],
        "bid_risk_items": [
            {
                "id": "br-001",
                "title": "风险",
                "summary": "风险摘要",
                "severity": "medium",
                "risk_category": "符合性",
                "source_excerpt": "摘录",
                "section_path": [],
                "confidence": "medium",
            }
        ],
        "directory_requirements": [],
    }
    normalized = normalize_interpretation_llm_data(
        data,
        section_path=["第二章 响应人须知"],
    )
    parsed = InterpretationLLMResponse.model_validate(normalized)
    assert parsed.disqualification_items[0].confidence == 0.9
    assert parsed.scoring_items[0].summary == "按细则评分"
    assert parsed.scoring_items[0].weight == "1"
    assert parsed.scoring_items[0].section_path == ["第二章 响应人须知"]
    assert parsed.bid_risk_items[0].confidence == 0.7


def test_normalize_wraps_directory_requirements_dict() -> None:
    data = {
        "disqualification_items": [],
        "scoring_items": [],
        "bid_risk_items": [],
        "directory_requirements": {
            "inferred": False,
            "required_sections": ["投标文件组成"],
            "mandatory": True,
            "structure": [{"order": 1, "title": "投标函", "mandatory": True, "children": []}],
            "source_excerpt": "原文",
            "confidence": 0.99,
        },
    }
    normalized = normalize_interpretation_llm_data(data)
    parsed = InterpretationLLMResponse.model_validate(normalized)
    assert len(parsed.directory_requirements) == 1
    assert parsed.directory_requirements[0].title == "投标文件组成"
    assert parsed.directory_requirements[0].id == "dir-001"


def test_normalize_coerces_fractional_structure_order() -> None:
    data = {
        "disqualification_items": [],
        "scoring_items": [],
        "bid_risk_items": [],
        "directory_requirements": [
            {
                "id": "dr-001",
                "title": "组成",
                "required_sections": [],
                "mandatory": True,
                "structure": [
                    {
                        "order": 2,
                        "title": "商务",
                        "mandatory": True,
                        "children": [
                            {"order": 2.1, "title": "资质", "mandatory": True, "children": []},
                            {"order": 2.2, "title": "业绩", "mandatory": True, "children": []},
                        ],
                    }
                ],
                "source_excerpt": "x",
                "section_path": [],
                "confidence": 0.8,
            }
        ],
    }
    normalized = normalize_interpretation_llm_data(data)
    parsed = InterpretationLLMResponse.model_validate(normalized)
    children = parsed.directory_requirements[0].structure[0].children
    assert children[0].order == 2
    assert children[1].order == 2
