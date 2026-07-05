from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from agent_platform.backends.platform import PlatformBackend
from agent_platform.models import AgentInvokeError


def test_platform_backend_maps_structured_output():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps(
        {
            "status": "completed",
            "structuredOutput": {"change_summary": "done"},
            "output": "",
        }
    ).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=fake_resp):
        backend = PlatformBackend(base_url="http://localhost:8000")
        result = backend.invoke("outline_refine", {"instruction": "x"})

    assert result.status == "completed"
    assert result.structured_output == {"change_summary": "done"}
    assert result.raw_response["status"] == "completed"


def test_platform_backend_raises_on_non_completed_status():
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"status": "failed", "error": "boom"}).encode("utf-8")
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=fake_resp):
        backend = PlatformBackend(base_url="http://localhost:8000")
        try:
            backend.invoke("outline_refine", {})
            assert False, "expected AgentInvokeError"
        except AgentInvokeError as exc:
            assert "failed" in str(exc)
