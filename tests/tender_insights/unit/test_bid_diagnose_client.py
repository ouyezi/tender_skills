from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tender_insights.bid_diagnose.client import (
    APP_NAME,
    BidDiagnoseClient,
    BidDiagnoseInvokeError,
    create_bid_diagnose_client_from_env,
)


def test_client_parses_import_diagnose_output():
    client = BidDiagnoseClient(base_url="http://example.com", api_key="key", timeout_s=30)
    body = json.dumps(
        {
            "status": "completed",
            "structuredOutput": {"import_diagnose": "重点"},
        }
    ).encode()

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return body

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        result = client.invoke({"current_task": "import_diagnose"})

    assert result.output == {"import_diagnose": "重点"}
    assert result.duration_ms >= 0


def test_client_rejects_empty_output_field():
    client = BidDiagnoseClient(base_url="http://example.com", api_key="key", timeout_s=30)
    body = json.dumps({"status": "completed", "structuredOutput": {"import_diagnose": "  "}}).encode()

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return body

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        with pytest.raises(BidDiagnoseInvokeError, match="empty import_diagnose"):
            client.invoke({"current_task": "import_diagnose"})


def test_client_falls_back_to_plain_text_output():
    client = BidDiagnoseClient(base_url="http://example.com", api_key="key", timeout_s=30)
    body = json.dumps(
        {
            "status": "completed",
            "output": "# 诊断重点\n\n- 格式核对",
        }
    ).encode()

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return body

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        result = client.invoke({"current_task": "import_diagnose"})

    assert result.output == {"import_diagnose": "# 诊断重点\n\n- 格式核对"}


def test_client_rejects_missing_output():
    client = BidDiagnoseClient(base_url="http://example.com", api_key="key", timeout_s=30)
    body = json.dumps({"status": "completed"}).encode()

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return body

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        with pytest.raises(BidDiagnoseInvokeError, match="empty import_diagnose"):
            client.invoke({"current_task": "import_diagnose"})


def test_create_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("AGENT_PLATFORM_API_KEY", raising=False)
    with pytest.raises(BidDiagnoseInvokeError, match="API_KEY"):
        create_bid_diagnose_client_from_env()


def test_app_name():
    assert APP_NAME == "bid_diagnose_app"
