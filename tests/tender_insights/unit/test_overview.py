import json

from doc_chunk.llm.client import FakeLLMClient

from tender_insights.interpret.models import InterpretationOverview
from tender_insights.interpret.overview import build_overview


def test_build_overview_calls_llm() -> None:
    client = FakeLLMClient(
        default_response=json.dumps(
            {
                "summary": "总览",
                "disqualification_summary": "废标概要",
                "scoring_summary": "得分概要",
                "bid_risk_summary": "风险概要",
                "directory_summary": "目录概要",
            }
        )
    )
    result = build_overview(client, dq=[], sc=[], br=[], dr=[])
    assert isinstance(result, InterpretationOverview)
    assert result.summary == "总览"
    assert client.calls
