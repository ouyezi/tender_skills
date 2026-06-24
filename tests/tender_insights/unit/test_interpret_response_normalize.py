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
