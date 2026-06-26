from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from doc_chunk.llm.client import LLMClient
from doc_chunk.llm.openai_client import create_llm_client_from_env
from doc_chunk.models.outline import OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.api import (
    extract_tender_brief,
    prepare_workspaces,
    run_interpret_job,
    run_template_job as api_run_template_job,
)
from tender_insights.common.content_source import prepare_interpret_source
from tender_insights.common.segment_planner import plan_segments
from tender_insights.config import InsightsConfig

from viewer.models import SessionRecord
from viewer.services.interpret_job_registry import InterpretJobRegistry
from viewer.services.interpret_session_store import InterpretSessionStore
from viewer.services.session_store import SessionStore

_PIPELINE_SUBSTEPS = 4
_LOGGER = logging.getLogger("viewer.interpret")


_STAGE_LABELS = {
    "extract": "提取正文",
    "outline": "构建目录",
    "tree": "构建文档树",
    "chunk": "分块",
}

_TEMPLATE_STAGE_LABELS = {
    "template_plan": "规划模版分片",
    "template_extract": "提取模版",
    "template_merge": "合并模版",
}


class InterpretPipelineService:
    def __init__(
        self,
        *,
        sessions: InterpretSessionStore,
        jobs: InterpretJobRegistry,
        viewer_sessions: SessionStore | None = None,
        llm_client_factory: Callable[[], LLMClient] | None = None,
    ) -> None:
        self._sessions = sessions
        self._jobs = jobs
        self._viewer_sessions = viewer_sessions
        self._llm_client_factory = llm_client_factory or create_llm_client_from_env

    def _count_interpret_nodes(self, workspace_dir: Path) -> int:
        ws = OutputWorkspace.open_existing(workspace_dir)
        outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))
        config = InsightsConfig.from_env()
        source = prepare_interpret_source(ws, config=config)
        return len(plan_segments(ws, source, outline, config=config))

    def _report(
        self,
        job_id: str,
        *,
        stage: str,
        message: str,
        step_current: int,
        step_total: int,
        detail: str = "",
        dual_file: bool,
        status: str = "running",
        segment_current: int = 0,
        segment_total: int = 0,
    ) -> None:
        percent = int(step_current * 100 / step_total) if step_total else 0
        self._jobs.update(
            job_id,
            stage=stage,
            message=message,
            status=status,
            progress_percent=min(percent, 100),
            step_current=step_current,
            step_total=step_total,
            segment_current=segment_current,
            segment_total=segment_total,
            detail=detail,
            dual_file=dual_file,
        )

    async def run_job(
        self,
        *,
        job_id: str,
        session_id: str,
        input_paths: list[Path],
        workspace_dir: Path,
    ) -> None:
        dual_file = len(input_paths) > 1
        step = 0
        try:
            pipeline_steps = len(input_paths) * _PIPELINE_SUBSTEPS + (1 if dual_file else 0)
            step_total = pipeline_steps + 2
            self._report(
                job_id,
                stage="pipeline_1",
                message="准备提取文件",
                step_current=step,
                step_total=step_total,
                dual_file=dual_file,
            )

            def _pipeline_progress(substage: str, payload: dict) -> None:
                nonlocal step
                if substage == "merge":
                    stage = "merge"
                    file_label = "合并"
                    sub_label = str(payload.get("message", "合并工作区"))
                else:
                    file_index = int(payload.get("file_index", 1))
                    stage = "pipeline_1" if file_index == 1 else "pipeline_2"
                    file_label = f"文件 {file_index}"
                    sub_label = _STAGE_LABELS.get(substage, substage)
                step += 1
                self._report(
                    job_id,
                    stage=stage,
                    message=f"{file_label}：{sub_label}",
                    step_current=step,
                    step_total=step_total,
                    detail=str(payload.get("message", "")),
                    dual_file=dual_file,
                )

            ws = await asyncio.to_thread(
                prepare_workspaces,
                input_paths,
                output_dir=workspace_dir,
                overwrite=True,
                on_progress=_pipeline_progress,
            )

            interpret_nodes = max(self._count_interpret_nodes(workspace_dir), 1)
            step_total = pipeline_steps + interpret_nodes + 1
            interpret_base = step
            self._report(
                job_id,
                stage="interpret",
                message=f"开始解读，共 {interpret_nodes} 个分段",
                step_current=interpret_base,
                step_total=step_total,
                detail="",
                dual_file=dual_file,
            )

            client = self._llm_client_factory()
            model_name = getattr(client, "model", None)
            if model_name:
                _LOGGER.info("interpret_llm_client model=%s", model_name)

            def _interpret_progress(stage: str, payload: dict) -> None:
                nonlocal step_total
                if stage.startswith("template_"):
                    template_total = int(payload.get("total", 1))
                    template_current = int(payload.get("current", 0))
                    template_base = interpret_base + interpret_nodes
                    expanded_total = template_base + template_total
                    if expanded_total > step_total:
                        step_total = expanded_total
                    step_current = template_base + template_current
                    self._report(
                        job_id,
                        stage="template",
                        message=_TEMPLATE_STAGE_LABELS.get(stage, "提取模版"),
                        step_current=min(step_current, step_total - 1),
                        step_total=step_total,
                        detail=str(payload.get("detail", "")),
                        dual_file=dual_file,
                    )
                    return
                seg_current = int(payload.get("current", 0))
                seg_total = int(payload.get("total", 1))
                step_current = interpret_base + seg_current
                self._report(
                    job_id,
                    stage="interpret",
                    message="解读招标",
                    step_current=min(step_current, step_total - 1),
                    step_total=step_total,
                    segment_current=seg_current,
                    segment_total=seg_total,
                    detail=str(payload.get("detail", "")),
                    dual_file=dual_file,
                )

            await asyncio.to_thread(
                run_interpret_job,
                ws,
                client=client,
                on_progress=_interpret_progress,
                setup_logging=True,
            )

            self._jobs.update(
                job_id,
                stage="done",
                message="解读完成",
                status="done",
                progress_percent=100,
                step_current=step_total,
                step_total=step_total,
                detail="",
                dual_file=dual_file,
            )
            session = self._sessions.update(session_id, status="success", error=None)
            if self._viewer_sessions is not None:
                from datetime import UTC, datetime

                now = datetime.now(UTC).isoformat()
                self._viewer_sessions.add(
                    SessionRecord(
                        id=session_id,
                        title=session.title,
                        workspace_path=str(workspace_dir),
                        source_type="upload",
                        status="success",
                        created_at=session.created_at,
                        opened_at=now,
                        error=None,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            self._jobs.update(
                job_id,
                stage="failed",
                message=message,
                status="failed",
                error=message,
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="failed", error=message)

    async def run_brief_on_workspace(
        self,
        *,
        job_id: str,
        session_id: str,
        workspace_dir: Path,
        dual_file: bool = False,
    ) -> None:
        try:
            latest_step_total = 1
            ws = OutputWorkspace.open_existing(workspace_dir)
            self._report(
                job_id,
                stage="brief",
                message="提取招标基础概要",
                step_current=0,
                step_total=latest_step_total,
                detail="",
                dual_file=dual_file,
            )
            client = self._llm_client_factory()

            def _brief_progress(_stage: str, payload: dict) -> None:
                nonlocal latest_step_total
                seg_current = int(payload.get("current", 0))
                seg_total = int(payload.get("total", 1))
                latest_step_total = int(payload.get("step_total", max(seg_total, 1)))
                step_current = int(payload.get("step_current", seg_current))
                self._report(
                    job_id,
                    stage="brief",
                    message=str(payload.get("message", "提取招标基础概要")),
                    step_current=step_current,
                    step_total=latest_step_total,
                    segment_current=seg_current,
                    segment_total=seg_total,
                    detail=str(payload.get("detail", "")),
                    dual_file=dual_file,
                )

            await asyncio.to_thread(
                extract_tender_brief,
                ws,
                client=client,
                on_progress=_brief_progress,
            )
            self._jobs.update(
                job_id,
                stage="done",
                message="概要提取完成",
                status="done",
                progress_percent=100,
                step_current=latest_step_total,
                step_total=latest_step_total,
                detail="",
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="success", error=None)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            self._jobs.update(
                job_id,
                stage="failed",
                message=message,
                status="failed",
                error=message,
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="failed", error=message)

    async def run_interpret_on_workspace(
        self,
        *,
        job_id: str,
        session_id: str,
        workspace_dir: Path,
        dual_file: bool = False,
    ) -> None:
        try:
            interpret_nodes = max(self._count_interpret_nodes(workspace_dir), 1)
            step_total = interpret_nodes + 1
            ws = OutputWorkspace.open_existing(workspace_dir)
            self._report(
                job_id,
                stage="interpret",
                message=f"开始解读，共 {interpret_nodes} 个分段",
                step_current=0,
                step_total=step_total,
                detail="",
                dual_file=dual_file,
            )
            client = self._llm_client_factory()
            model_name = getattr(client, "model", None)
            if model_name:
                _LOGGER.info("interpret_llm_client model=%s", model_name)

            def _interpret_progress(stage: str, payload: dict) -> None:
                nonlocal step_total
                if stage.startswith("template_"):
                    template_total = int(payload.get("total", 1))
                    template_current = int(payload.get("current", 0))
                    template_base = interpret_nodes
                    expanded_total = template_base + template_total
                    if expanded_total > step_total:
                        step_total = expanded_total
                    step_current = template_base + template_current
                    self._report(
                        job_id,
                        stage="template",
                        message=_TEMPLATE_STAGE_LABELS.get(stage, "提取模版"),
                        step_current=min(step_current, step_total - 1),
                        step_total=step_total,
                        detail=str(payload.get("detail", "")),
                        dual_file=dual_file,
                    )
                    return
                seg_current = int(payload.get("current", 0))
                seg_total = int(payload.get("total", 1))
                step_current = seg_current
                self._report(
                    job_id,
                    stage="interpret",
                    message="解读招标",
                    step_current=min(step_current, step_total - 1),
                    step_total=step_total,
                    segment_current=seg_current,
                    segment_total=seg_total,
                    detail=str(payload.get("detail", "")),
                    dual_file=dual_file,
                )

            await asyncio.to_thread(
                run_interpret_job,
                ws,
                client=client,
                on_progress=_interpret_progress,
                setup_logging=True,
            )
            self._jobs.update(
                job_id,
                stage="done",
                message="解读完成",
                status="done",
                progress_percent=100,
                step_current=step_total,
                step_total=step_total,
                detail="",
                dual_file=dual_file,
            )
            session = self._sessions.update(session_id, status="success", error=None)
            if self._viewer_sessions is not None:
                from datetime import UTC, datetime

                now = datetime.now(UTC).isoformat()
                self._viewer_sessions.add(
                    SessionRecord(
                        id=session_id,
                        title=session.title,
                        workspace_path=str(workspace_dir),
                        source_type="upload",
                        status="success",
                        created_at=session.created_at,
                        opened_at=now,
                        error=None,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            self._jobs.update(
                job_id,
                stage="failed",
                message=message,
                status="failed",
                error=message,
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="failed", error=message)

    async def run_brief_job(
        self,
        *,
        job_id: str,
        session_id: str,
        input_paths: list[Path],
        workspace_dir: Path,
    ) -> None:
        dual_file = len(input_paths) > 1
        step = 0
        try:
            pipeline_steps = len(input_paths) * _PIPELINE_SUBSTEPS + (1 if dual_file else 0)
            step_total = pipeline_steps + 1
            self._report(
                job_id,
                stage="pipeline_1",
                message="准备提取文件",
                step_current=step,
                step_total=step_total,
                dual_file=dual_file,
            )

            def _pipeline_progress(substage: str, payload: dict) -> None:
                nonlocal step
                if substage == "merge":
                    stage = "merge"
                    file_label = "合并"
                    sub_label = str(payload.get("message", "合并工作区"))
                else:
                    file_index = int(payload.get("file_index", 1))
                    stage = "pipeline_1" if file_index == 1 else "pipeline_2"
                    file_label = f"文件 {file_index}"
                    sub_label = _STAGE_LABELS.get(substage, substage)
                step += 1
                self._report(
                    job_id,
                    stage=stage,
                    message=f"{file_label}：{sub_label}",
                    step_current=step,
                    step_total=step_total,
                    detail=str(payload.get("message", "")),
                    dual_file=dual_file,
                )

            ws = await asyncio.to_thread(
                prepare_workspaces,
                input_paths,
                output_dir=workspace_dir,
                overwrite=True,
                on_progress=_pipeline_progress,
            )

            brief_base = pipeline_steps
            self._report(
                job_id,
                stage="brief",
                message="提取招标基础概要",
                step_current=brief_base,
                step_total=brief_base + 1,
                detail="",
                dual_file=dual_file,
            )

            client = self._llm_client_factory()

            def _brief_progress(_stage: str, payload: dict) -> None:
                seg_current = int(payload.get("current", 0))
                seg_total = int(payload.get("total", 1))
                step_total_val = int(payload.get("step_total", max(seg_total, 1)))
                step_current = int(payload.get("step_current", seg_current))
                self._report(
                    job_id,
                    stage="brief",
                    message=str(payload.get("message", "提取招标基础概要")),
                    step_current=brief_base + step_current,
                    step_total=brief_base + step_total_val,
                    segment_current=seg_current,
                    segment_total=seg_total,
                    detail=str(payload.get("detail", "")),
                    dual_file=dual_file,
                )

            await asyncio.to_thread(
                extract_tender_brief,
                ws,
                client=client,
                on_progress=_brief_progress,
            )

            self._jobs.update(
                job_id,
                stage="done",
                message="概要提取完成",
                status="done",
                progress_percent=100,
                step_current=step_total,
                step_total=step_total,
                detail="",
                dual_file=dual_file,
            )
            session = self._sessions.update(session_id, status="success", error=None)
            if self._viewer_sessions is not None:
                from datetime import UTC, datetime

                now = datetime.now(UTC).isoformat()
                self._viewer_sessions.add(
                    SessionRecord(
                        id=session_id,
                        title=session.title,
                        workspace_path=str(workspace_dir),
                        source_type="upload",
                        status="success",
                        created_at=session.created_at,
                        opened_at=now,
                        error=None,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            self._jobs.update(
                job_id,
                stage="failed",
                message=message,
                status="failed",
                error=message,
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="failed", error=message)

    async def run_template_on_workspace(
        self,
        *,
        job_id: str,
        session_id: str,
        workspace_dir: Path,
        dual_file: bool = False,
    ) -> None:
        try:
            latest_step_total = 1
            ws = OutputWorkspace.open_existing(workspace_dir)
            self._report(
                job_id,
                stage="template_plan",
                message="规划模版分片",
                step_current=0,
                step_total=latest_step_total,
                detail="",
                dual_file=dual_file,
            )
            client = self._llm_client_factory()

            def _template_progress(stage: str, payload: dict) -> None:
                nonlocal latest_step_total
                current = int(payload.get("current", 0))
                total = int(payload.get("total", 1))
                latest_step_total = max(latest_step_total, total)
                message = _TEMPLATE_STAGE_LABELS.get(stage, "提取模版")
                if stage == "template_extract" and total > 2:
                    shard_num = min(current, total - 2)
                    message = f"提取模版 ({shard_num}/{total - 2})"
                self._report(
                    job_id,
                    stage=stage,
                    message=message,
                    step_current=current,
                    step_total=latest_step_total,
                    detail=str(payload.get("detail", "")),
                    dual_file=dual_file,
                )

            await asyncio.to_thread(
                api_run_template_job,
                ws,
                client=client,
                on_progress=_template_progress,
            )
            self._jobs.update(
                job_id,
                stage="done",
                message="模版提取完成",
                status="done",
                progress_percent=100,
                step_current=latest_step_total,
                step_total=latest_step_total,
                detail="",
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="success", error=None)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            self._jobs.update(
                job_id,
                stage="failed",
                message=message,
                status="failed",
                error=message,
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="failed", error=message)

    async def run_template_job(
        self,
        *,
        job_id: str,
        session_id: str,
        input_paths: list[Path],
        workspace_dir: Path,
    ) -> None:
        dual_file = len(input_paths) > 1
        step = 0
        try:
            pipeline_steps = len(input_paths) * _PIPELINE_SUBSTEPS + (1 if dual_file else 0)
            step_total = pipeline_steps + 1
            self._report(
                job_id,
                stage="pipeline_1",
                message="准备提取文件",
                step_current=step,
                step_total=step_total,
                dual_file=dual_file,
            )

            def _pipeline_progress(substage: str, payload: dict) -> None:
                nonlocal step
                if substage == "merge":
                    stage = "merge"
                    file_label = "合并"
                    sub_label = str(payload.get("message", "合并工作区"))
                else:
                    file_index = int(payload.get("file_index", 1))
                    stage = "pipeline_1" if file_index == 1 else "pipeline_2"
                    file_label = f"文件 {file_index}"
                    sub_label = _STAGE_LABELS.get(substage, substage)
                step += 1
                self._report(
                    job_id,
                    stage=stage,
                    message=f"{file_label}：{sub_label}",
                    step_current=step,
                    step_total=step_total,
                    detail=str(payload.get("message", "")),
                    dual_file=dual_file,
                )

            ws = await asyncio.to_thread(
                prepare_workspaces,
                input_paths,
                output_dir=workspace_dir,
                overwrite=True,
                on_progress=_pipeline_progress,
            )

            template_base = pipeline_steps
            latest_step_total = template_base + 1
            self._report(
                job_id,
                stage="template_plan",
                message="规划模版分片",
                step_current=template_base,
                step_total=latest_step_total,
                detail="",
                dual_file=dual_file,
            )

            client = self._llm_client_factory()

            def _template_progress(stage: str, payload: dict) -> None:
                nonlocal latest_step_total
                current = int(payload.get("current", 0))
                total = int(payload.get("total", 1))
                latest_step_total = max(template_base + total, latest_step_total)
                message = _TEMPLATE_STAGE_LABELS.get(stage, "提取模版")
                if stage == "template_extract" and total > 2:
                    shard_num = min(current, total - 2)
                    message = f"提取模版 ({shard_num}/{total - 2})"
                self._report(
                    job_id,
                    stage=stage,
                    message=message,
                    step_current=template_base + current,
                    step_total=latest_step_total,
                    detail=str(payload.get("detail", "")),
                    dual_file=dual_file,
                )

            await asyncio.to_thread(
                api_run_template_job,
                ws,
                client=client,
                on_progress=_template_progress,
            )

            self._jobs.update(
                job_id,
                stage="done",
                message="模版提取完成",
                status="done",
                progress_percent=100,
                step_current=latest_step_total,
                step_total=latest_step_total,
                detail="",
                dual_file=dual_file,
            )
            session = self._sessions.update(session_id, status="success", error=None)
            if self._viewer_sessions is not None:
                from datetime import UTC, datetime

                now = datetime.now(UTC).isoformat()
                self._viewer_sessions.add(
                    SessionRecord(
                        id=session_id,
                        title=session.title,
                        workspace_path=str(workspace_dir),
                        source_type="upload",
                        status="success",
                        created_at=session.created_at,
                        opened_at=now,
                        error=None,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            self._jobs.update(
                job_id,
                stage="failed",
                message=message,
                status="failed",
                error=message,
                dual_file=dual_file,
            )
            self._sessions.update(session_id, status="failed", error=message)
