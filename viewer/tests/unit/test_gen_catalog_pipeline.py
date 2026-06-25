from __future__ import annotations

from viewer.services.gen_catalog_pipeline import GenCatalogPipelineService
from viewer.services.interpret_job_registry import InterpretJobRegistry
from viewer.services.interpret_session_store import InterpretSessionStore


def test_gen_catalog_pipeline_service_constructed(viewer_data_dir) -> None:
    sessions = InterpretSessionStore(viewer_data_dir / "interpret_sessions.json")
    jobs = InterpretJobRegistry()
    service = GenCatalogPipelineService(sessions=sessions, jobs=jobs)
    assert service is not None
