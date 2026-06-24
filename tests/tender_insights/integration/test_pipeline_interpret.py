import json

from doc_chunk.llm.client import FakeLLMClient

from tender_insights.api import interpret_document, resolve_workspace_path
from tender_insights.interpret.models import InterpretationFile


def test_interpret_writes_json(sample_docx, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCR_ENABLED", "false")

    ws = resolve_workspace_path(sample_docx, output_dir=tmp_path / "ws", overwrite=True)
    segment_json = json.dumps(
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
    overview_json = json.dumps(
        {
            "summary": "概要",
            "disqualification_summary": "废标概要",
            "scoring_summary": "得分概要",
            "bid_risk_summary": "风险概要",
            "directory_summary": "目录概要",
        }
    )
    fake = FakeLLMClient(responses=[segment_json, overview_json])
    result = interpret_document(ws, client=fake)
    assert isinstance(result, InterpretationFile)
    assert (ws.root / "interpretation.json").exists()
    assert len(result.disqualification_items) >= 1
    assert result.overview.summary == "概要"
    assert result.segment_count >= 1
