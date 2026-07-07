from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tender_insights.diagnosis.client import (
    APP_NAME,
    DiagnosisClient,
    create_diagnosis_client_from_env,
)
from tender_insights.diagnosis.models import (
    ChunkSummaryOutput,
    DiagnosisInvokeError,
    DiagnosisInvokeTimeoutError,
)


def test_invoke_returns_structured_output():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps(
        {
            "status": "completed",
            "structuredOutput": {
                "current_summary": "当前",
                "total_summary": "整体",
            },
        }
    ).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    captured: dict = {}

    def _urlopen(req, timeout):
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return fake_resp

    client = DiagnosisClient(
        base_url="http://localhost:8000",
        api_key="test-key",
        timeout_s=600,
    )

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        result = client.invoke({"chunk": "x", "current_count": "1"})

    assert result.output == ChunkSummaryOutput(current_summary="当前", total_summary="整体")
    assert captured["timeout"] == 600
    assert captured["body"]["appName"] == APP_NAME
    assert captured["headers"]["X-api-key"] == "test-key"


def test_invoke_raises_on_missing_structured_output():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"status": "completed", "output": "text only"}).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    client = DiagnosisClient(base_url="http://localhost:8000", api_key="k", timeout_s=600)
    with patch("urllib.request.urlopen", return_value=fake_resp):
        with pytest.raises(DiagnosisInvokeError, match="structured"):
            client.invoke({})


def test_invoke_timeout_maps_to_timeout_error():
    import socket
    import urllib.error

    client = DiagnosisClient(base_url="http://localhost:8000", api_key="k", timeout_s=600)
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError(socket.timeout("timed out")),
    ):
        with pytest.raises(DiagnosisInvokeTimeoutError) as exc_info:
            client.invoke({})
    assert exc_info.value.configured_timeout_s == 600


def test_create_client_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_PLATFORM_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("AGENT_PLATFORM_API_KEY", "env-key")
    monkeypatch.setenv("DIAGNOSIS_INVOKE_TIMEOUT_S", "300")
    client = create_diagnosis_client_from_env()
    assert client.timeout_s == 300
    assert client.api_key == "env-key"
