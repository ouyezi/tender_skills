from __future__ import annotations

from functools import lru_cache

from viewer.config import ViewerSettings
from viewer.services.interpret_job_registry import InterpretJobRegistry
from viewer.services.interpret_pipeline import InterpretPipelineService
from viewer.services.interpret_session_store import InterpretSessionStore
from viewer.services.job_registry import JobRegistry
from viewer.services.pipeline import PipelineService
from viewer.services.session_store import SessionStore


@lru_cache
def get_settings() -> ViewerSettings:
    return ViewerSettings.load()


@lru_cache
def get_session_store() -> SessionStore:
    settings = get_settings()
    return SessionStore(settings.sessions_file, max_sessions=settings.max_sessions)


@lru_cache
def get_interpret_session_store() -> InterpretSessionStore:
    settings = get_settings()
    return InterpretSessionStore(settings.interpret_sessions_file, max_sessions=settings.max_sessions)


@lru_cache
def get_job_registry() -> JobRegistry:
    return JobRegistry()


@lru_cache
def get_interpret_job_registry() -> InterpretJobRegistry:
    return InterpretJobRegistry()


@lru_cache
def get_pipeline_service() -> PipelineService:
    return PipelineService(sessions=get_session_store(), jobs=get_job_registry())


@lru_cache
def get_interpret_pipeline_service() -> InterpretPipelineService:
    return InterpretPipelineService(
        sessions=get_interpret_session_store(),
        jobs=get_interpret_job_registry(),
    )
