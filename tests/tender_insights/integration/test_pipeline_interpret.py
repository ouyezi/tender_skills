import json

from doc_chunk.llm.client import FakeLLMClient

from tender_insights.api import interpret_document, resolve_workspace_path
from tender_insights.interpret.models import InterpretationFile


def test_interpret_writes_json(sample_docx, tmp_path) -> None:
    ws = resolve_workspace_path(sample_docx, output_dir=tmp_path / "ws", overwrite=True)
    fake = FakeLLMClient(
        default_response=json.dumps(
            {
                "disqualification_items": [
                    {
                        "id": "dq-001",
                        "title": "测试废标",
                        "summary": "s",
                        "trigger_condition": "t",
                        "source_excerpt": "废标条款",
                        "section_path": ["投标人须知"],
                        "confidence": 0.9,
                    }
                ],
                "scoring_items": [],
                "bid_risk_items": [],
                "directory_requirements": [],
            }
        )
    )
    result = interpret_document(ws, client=fake)
    assert isinstance(result, InterpretationFile)
    assert (ws.root / "interpretation.json").exists()
    assert len(result.disqualification_items) >= 1
