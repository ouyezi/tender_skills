from __future__ import annotations

import json

from agent_platform.backends.local import LocalBackend
from agent_platform.client import AgentClient
from doc_chunk.llm.client import FakeLLMClient


OUTLINE_REFINE_RESPONSE = (
    '{"outline_refined":{"schema_version":"1.0","strategy":"heading_heuristic","nodes":[]},'
    '"node_mappings":[],"change_summary":"ok"}'
)


def test_local_backend_outline_refine_returns_structured_output():
    llm = FakeLLMClient(responses=[OUTLINE_REFINE_RESPONSE])
    client = AgentClient(LocalBackend(llm_client=llm))
    result = client.invoke(
        "outline_refine",
        {
            "instruction": "test",
            "original_outline": {"schema_version": "1.0", "nodes": []},
            "current_outline": {"schema_version": "1.0", "nodes": []},
        },
    )
    assert result.status == "completed"
    assert result.structured_output is not None
    assert result.structured_output["change_summary"] == "ok"
    assert len(llm.calls) == 1
    user_msg = llm.calls[0]["messages"][1]["content"]
    payload = json.loads(user_msg)
    assert payload["instruction"] == "test"


def test_local_backend_unknown_call_type_raises():
    llm = FakeLLMClient()
    backend = LocalBackend(llm_client=llm)
    try:
        backend.invoke("unknown_agent", {})
        assert False, "expected AgentInvokeError"
    except Exception as exc:
        from agent_platform.models import AgentInvokeError

        assert isinstance(exc, AgentInvokeError)
        assert "unknown_agent" in str(exc)


def test_local_backend_chunk_classify_returns_structured_output():
    llm = FakeLLMClient(
        responses=[
            '{"knowledge_type":"scheme","chapter_type":"技术方案",'
            '"confidence":0.9,"rationale":"ok"}'
        ]
    )
    client = AgentClient(LocalBackend(llm_client=llm))
    result = client.invoke(
        "chunk_classify",
        {"title": "技术方案", "markdown": "云原生架构"},
    )
    assert result.status == "completed"
    assert result.structured_output is not None
    assert result.structured_output["knowledge_type"] == "scheme"


def test_local_backend_chunk_describe_returns_text_output():
    llm = FakeLLMClient(responses=["这是一段摘要。"])
    client = AgentClient(LocalBackend(llm_client=llm))
    result = client.invoke(
        "chunk_describe",
        {"title": "概述", "markdown": "建设招标处理系统"},
    )
    assert result.status == "completed"
    assert result.text_output == "这是一段摘要。"
    assert result.structured_output is None


def test_local_backend_ocr_requires_ocr_client():
    from agent_platform.models import AgentInvokeError

    backend = LocalBackend(llm_client=FakeLLMClient())
    try:
        backend.invoke("ocr_image_recognize", {"image_url": "data:image/png;base64,xx"})
        assert False, "expected AgentInvokeError"
    except AgentInvokeError as exc:
        assert "ocr_client" in str(exc)


def test_local_backend_interpret_segment_returns_structured_output():
    llm = FakeLLMClient(
        responses=[
            '{"disqualification_items":[],"scoring_items":[],'
            '"bid_risk_items":[],"directory_requirements":[]}'
        ]
    )
    client = AgentClient(LocalBackend(llm_client=llm))
    result = client.invoke(
        "interpret_segment",
        {
            "segment_id": "seg-001",
            "section_path": "第一章 > 须知",
            "markdown": "投标人须提交营业执照。",
        },
    )
    assert result.status == "completed"
    assert result.structured_output is not None
    assert result.structured_output["disqualification_items"] == []


def test_local_backend_interpret_overview_returns_structured_output():
    llm = FakeLLMClient(
        responses=[
            '{"summary":"s","disqualification_summary":"d","scoring_summary":"sc",'
            '"bid_risk_summary":"b","directory_summary":"dir"}'
        ]
    )
    client = AgentClient(LocalBackend(llm_client=llm))
    result = client.invoke(
        "interpret_overview",
        {"items_json": '{"disqualification_items":[]}'},
    )
    assert result.status == "completed"
    assert result.structured_output is not None
    assert result.structured_output["summary"] == "s"


def test_local_backend_ocr_image_recognize_returns_text():
    class _FakeOcr:
        def recognize_image_url(self, image_url: str) -> str:
            assert image_url.startswith("data:")
            return "OCR 文本"

    client = AgentClient(
        LocalBackend(llm_client=FakeLLMClient(), ocr_client=_FakeOcr()),
    )
    result = client.invoke(
        "ocr_image_recognize",
        {"image_url": "data:image/png;base64,abc"},
    )
    assert result.status == "completed"
    assert result.text_output == "OCR 文本"
