from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path

from doc_chunk.api import run_pipeline
from doc_chunk.llm.client import LLMClient
from doc_chunk.llm.openai_client import create_llm_client_from_env
from doc_chunk.models.document import PipelineResult
from doc_chunk.models.outline import OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.api import extract_templates
from tender_insights.common.content_source import prepare_interpret_source
from tender_insights.common.segment_planner import plan_segments
from tender_insights.config import InsightsConfig
from tender_insights.interpret.extractor import interpret_workspace

from viewer.models import SessionRecord
from viewer.services.interpret_job_registry import InterpretJobRegistry
from viewer.services.interpret_session_store import InterpretSessionStore
from viewer.services.session_store import SessionStore
from viewer.services.workspace_merge import merge_workspaces, validate_merged_workspace

_PIPELINE_SUBSTEPS = 4
_STAGE_LABELS = {
    "extract": "提取正文",
    "outline": "构建目录",
    "tree": "构建文档树",
    "chunk": "分块",
}


class InterpretPipelineService:
    def __init__(
        self,
        *,
        sessions: InterpretSessionStore,
        jobs: InterpretJobRegistry,
        viewer_sessions: SessionStore | None = None,
        run_pipeline_fn: Callable[..., PipelineResult] = run_pipeline,
        llm_client_factory: Callable[[], LLMClient] | None = None,
    ) -> None:
        self._sessions = sessions
        self._jobs = jobs
        self._viewer_sessions = viewer_sessions
        self._run_pipeline = run_pipeline_fn
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
        temp_dirs: list[Path] = []
        dual_file = len(input_paths) > 1
        step = 0
        try:
            pipeline_steps = len(input_paths) * _PIPELINE_SUBSTEPS + (1 if dual_file else 0)
            step_total = pipeline_steps + 2  # interpret placeholder + template; refined after pipeline
            self._report(
                job_id,
                stage="pipeline_1",
                message="准备提取文件",
                step_current=step,
                step_total=step_total,
                dual_file=dual_file,
            )

            for idx, input_path in enumerate(input_paths, start=1):
                stage = "pipeline_1" if idx == 1 else "pipeline_2"
                file_label = f"文件 {idx}"

                def _progress(substage: str, payload: dict) -> None:
                    nonlocal step
                    step += 1
                    sub_label = _STAGE_LABELS.get(substage, substage)
                    self._report(
                        job_id,
                        stage=stage,
                        message=f"{file_label}：{sub_label}",
                        step_current=step,
                        step_total=step_total,
                        detail=str(payload.get("message", "")),
                        dual_file=dual_file,
                    )

                temp = workspace_dir.parent / f"{session_id}_tmp{idx}"
                temp_dirs.append(temp)
                result = await asyncio.to_thread(
                    self._run_pipeline,
                    input_path,
                    temp,
                    overwrite=True,
                    skip_refine=True,
                    skip_enrich=True,
                    on_progress=_progress,
                )
                if result.status == "failed":
                    error = result.errors[0]["error"] if result.errors else "pipeline failed"
                    raise RuntimeError(error)

            if len(input_paths) == 1:
                if workspace_dir.exists():
                    shutil.rmtree(workspace_dir)
                shutil.copytree(temp_dirs[0], workspace_dir)
            else:
                step += 1
                self._report(
                    job_id,
                    stage="merge",
                    message="合并工作区",
                    step_current=step,
                    step_total=step_total,
                    dual_file=dual_file,
                )
                if workspace_dir.exists():
                    shutil.rmtree(workspace_dir)
                merge_workspaces(
                    workspace_dir,
                    sources=[
                        (temp_dirs[0], input_paths[0].name),
                        (temp_dirs[1], input_paths[1].name),
                    ],
                )
                validate_merged_workspace(workspace_dir)

            interpret_nodes = max(self._count_interpret_nodes(workspace_dir), 1)
            step_total = pipeline_steps + interpret_nodes + 1  # +1 template
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

            ws = OutputWorkspace.open_existing(workspace_dir)
            client = self._llm_client_factory()

            def _interpret_progress(_stage: str, payload: dict) -> None:
                current = int(payload.get("current", 0))
                step_current = interpret_base + current
                self._report(
                    job_id,
                    stage="interpret",
                    message=str(payload.get("message", "解读招标")),
                    step_current=min(step_current, step_total - 1),
                    step_total=step_total,
                    detail=str(payload.get("detail", "")),
                    dual_file=dual_file,
                )

            await asyncio.to_thread(
                interpret_workspace,
                ws,
                client,
                on_progress=_interpret_progress,
            )

            step = step_total - 1
            self._report(
                job_id,
                stage="template",
                message="提取模版",
                step_current=step,
                step_total=step_total,
                dual_file=dual_file,
            )
            await asyncio.to_thread(extract_templates, ws, client=client)

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
        finally:
            for temp in temp_dirs:
                shutil.rmtree(temp, ignore_errors=True)
