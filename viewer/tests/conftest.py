from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

_conftest_path = ROOT / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location("repo_root_conftest", _conftest_path)
assert _spec is not None and _spec.loader is not None
_root_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_root_conftest)


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    return _root_conftest._build_sample_docx(tmp_path / "sample.docx", include_image=False)


@pytest.fixture
def viewer_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DOC_CHUNK_VIEWER_DATA", str(tmp_path))
    return tmp_path


@pytest.fixture
def interpret_client(viewer_data_dir, monkeypatch):
    import json

    from doc_chunk.llm.client import FakeLLMClient
    from fastapi.testclient import TestClient

    from viewer.deps import get_interpret_pipeline_service, get_settings
    from viewer.main import create_app
    from viewer.services.interpret_job_registry import InterpretJobRegistry
    from viewer.services.interpret_pipeline import InterpretPipelineService
    from viewer.services.interpret_session_store import InterpretSessionStore
    from viewer.services.session_store import SessionStore

    class _InterpretFakeLLM(FakeLLMClient):
        def __init__(self, *, segment_json: str, overview_json: str) -> None:
            super().__init__()
            self._segment_json = segment_json
            self._overview_json = overview_json

        def complete(self, messages, *, response_format="text", timeout=60.0):
            user_text = " ".join(
                str(m.get("content", "")) for m in messages if m.get("role") == "user"
            )
            if "已提取明细" in user_text:
                return self._overview_json
            return self._segment_json

    get_settings.cache_clear()
    get_interpret_pipeline_service.cache_clear()

    settings = get_settings()
    sessions = InterpretSessionStore(settings.interpret_sessions_file)
    jobs = InterpretJobRegistry()

    segment_json = json.dumps(
        {
            "disqualification_items": [
                {
                    "id": "dq-001",
                    "title": "测试废标",
                    "summary": "摘要",
                    "trigger_condition": "条件",
                    "source_excerpt": "原文",
                    "section_path": ["第一章"],
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
            "disqualification_summary": "废标",
            "scoring_summary": "得分",
            "bid_risk_summary": "风险",
            "directory_summary": "目录",
        }
    )
    fake = _InterpretFakeLLM(segment_json=segment_json, overview_json=overview_json)

    def factory():
        return InterpretPipelineService(
            sessions=sessions,
            jobs=jobs,
            viewer_sessions=SessionStore(settings.sessions_file),
            llm_client_factory=lambda: fake,
        )

    def get_jobs():
        return jobs

    def get_sessions():
        return sessions

    monkeypatch.setattr("viewer.deps.get_interpret_pipeline_service", factory)
    monkeypatch.setattr("viewer.routes.interpret.get_interpret_pipeline_service", factory)
    monkeypatch.setattr("viewer.deps.get_interpret_job_registry", get_jobs)
    monkeypatch.setattr("viewer.routes.interpret.get_interpret_job_registry", get_jobs)
    monkeypatch.setattr("viewer.deps.get_interpret_session_store", get_sessions)
    monkeypatch.setattr("viewer.routes.interpret.get_interpret_session_store", get_sessions)
    return TestClient(create_app())


@pytest.fixture
def second_sample_docx(sample_docx: Path, tmp_path: Path) -> Path:
    dest = tmp_path / "supplement.docx"
    dest.write_bytes(sample_docx.read_bytes())
    return dest


@pytest.fixture
def pipeline_workspace(sample_docx: Path, tmp_path: Path) -> Path:
    from doc_chunk.api import run_pipeline

    workspace = tmp_path / "workspace"
    result = run_pipeline(sample_docx, workspace, overwrite=True, skip_refine=True, skip_enrich=True)
    assert result.status == "success"
    return workspace
