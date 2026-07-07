from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tender_insights.summary_loop.client import (
    APP_NAME,
    SummaryLoopClient,
    create_summary_loop_client_from_env,
)
from tender_insights.summary_loop.models import (
    SummaryLoopInvokeError,
    SummaryLoopInvokeTimeoutError,
)


def test_invoke_returns_text_output():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps(
        {"status": "completed", "output": "概要文本", "structuredOutput": None}
    ).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    captured: dict = {}

    def _urlopen(req, timeout):
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return fake_resp

    client = SummaryLoopClient(
        base_url="http://localhost:8000",
        api_key="test-key",
        timeout_s=600,
    )

    with patch("urllib.request.urlopen", side_effect=_urlopen):
        result = client.invoke({"tender_info": "x", "current_task": "get_tender_summary"})

    assert result.output == "概要文本"
    assert captured["timeout"] == 600
    assert captured["body"]["appName"] == APP_NAME
    assert captured["headers"]["X-api-key"] == "test-key"


def test_invoke_raises_on_non_completed_status():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"status": "failed"}).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    client = SummaryLoopClient(base_url="http://localhost:8000", api_key="k", timeout_s=600)
    with patch("urllib.request.urlopen", return_value=fake_resp):
        with pytest.raises(SummaryLoopInvokeError, match="not completed"):
            client.invoke({})


def test_invoke_timeout_maps_to_timeout_error():
    import socket
    import urllib.error

    client = SummaryLoopClient(base_url="http://localhost:8000", api_key="k", timeout_s=600)
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError(socket.timeout("timed out")),
    ):
        with pytest.raises(SummaryLoopInvokeTimeoutError) as exc_info:
            client.invoke({})
    assert exc_info.value.configured_timeout_s == 600


def test_non_ascii_api_key_raises_clear_error():
    with pytest.raises(SummaryLoopInvokeError, match="ASCII characters"):
        SummaryLoopClient(base_url="http://localhost:8000", api_key="中文密钥", timeout_s=600)


def test_create_client_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_PLATFORM_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("AGENT_PLATFORM_API_KEY", "env-key")
    monkeypatch.setenv("SUMMARY_LOOP_INVOKE_TIMEOUT_S", "300")
    client = create_summary_loop_client_from_env()
    assert client.timeout_s == 300
    assert client.api_key == "env-key"
