from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Callable, Literal

from doc_chunk.chunk.planner import plan_chunks
from doc_chunk.chunk.refined_planner import plan_chunks_from_refined
from doc_chunk.chunk.writer import write_chunks
from doc_chunk.errors import LLMUnavailableError, UnsupportedFormatError, ValidationError, WorkspaceError
from doc_chunk.extract.detect import detect_file_type
from doc_chunk.extract.docx_extractor import extract_docx
from doc_chunk.extract.pdf_extractor import extract_pdf
from doc_chunk.llm.client import LLMClient
from doc_chunk.llm.openai_client import create_llm_client_from_env
from doc_chunk.metadata.classify import classify_chunk
from doc_chunk.metadata.describe import describe_chunk
from doc_chunk.models.chunk import ChunkIndex, ChunkIndexEntry, ContentChunk
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.models.document import PipelineResult
from doc_chunk.models.document_tree import DocumentTreeFile
from doc_chunk.models.manifest import Manifest, SourceInfo, StageStatus
from doc_chunk.models.linkage import LinkageFile
from doc_chunk.models.outline import OutlineMappingFile, OutlineTree
from doc_chunk.outline.builder import build_outline_from_workspace
from doc_chunk.outline_refine.engine import OutlineRefineEngine
from doc_chunk.outline_refine.persist import clear_refined_artifacts, persist_refined_artifacts
from doc_chunk.outline_refine.session import RefineSession
from doc_chunk.linkage.builder import build_linkage
from doc_chunk.tree.builder import build_document_tree_with_warnings
from doc_chunk.workspace.layout import OutputWorkspace
from doc_chunk.workspace.manifest_io import load_manifest, save_manifest

_REFINE_SESSIONS: dict[str, RefineSession] = {}


def _build_manifest(source_path: Path, file_type: str, warnings: list[str]) -> Manifest:
    stage = StageStatus(status="success", warnings=warnings)
    return Manifest(
        status="success",
        source=SourceInfo(
            path=str(source_path),
            file_name=source_path.name,
            file_type=file_type,  # type: ignore[arg-type]
            title=source_path.stem,
        ),
        stages={"extract": stage},
        outputs={
            "content": "content.md",
            "images": "images",
            "content_blocks": "content.blocks.json",
            "images_manifest": "images/manifest.json",
            "tables": "tables",
            "tables_index": "tables/index.json",
        },
        warnings=warnings,
    )


def extract_file(
    input_path: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
    promote_headings: Literal["off", "auto"] = "off",
) -> Manifest:
    source_path = Path(input_path)
    file_type = detect_file_type(source_path)
    workspace = OutputWorkspace.create(Path(output_dir), overwrite=overwrite)

    if file_type == "docm":
        raise UnsupportedFormatError(
            "docm is not supported directly; convert to docx first (e.g. tender_knowledge docm_converter)"
        )
    if file_type in {"docx"}:
        result = extract_docx(source_path, workspace, promote_headings=promote_headings)
    elif file_type == "pdf":
        result = extract_pdf(source_path, workspace)
    else:
        raise UnsupportedFormatError(f"Unsupported file type for extraction: {file_type}")

    manifest = _build_manifest(source_path, file_type, result.warnings)
    save_manifest(workspace, manifest)
    return manifest


def build_tree(workspace: Path) -> DocumentTreeFile:
    ws = OutputWorkspace.open_existing(Path(workspace))
    if not ws.content_blocks_path.exists():
        raise WorkspaceError(f"content.blocks.json not found: {ws.content_blocks_path}")
    if not ws.outline_path.exists():
        raise WorkspaceError(f"outline.json not found: {ws.outline_path}")

    blocks = ContentBlocksFile.model_validate_json(ws.content_blocks_path.read_text(encoding="utf-8"))
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))
    content_md = ws.content_path.read_text(encoding="utf-8")
    tree, tree_warnings = build_document_tree_with_warnings(blocks, outline, content_md=content_md)
    ws.document_tree_path.write_text(tree.model_dump_json(indent=2), encoding="utf-8")

    if ws.manifest_path.exists():
        manifest = load_manifest(ws.manifest_path)
        manifest.stages["tree"] = StageStatus(status="success")
        manifest.outputs["document_tree"] = "document_tree.json"
        for warning in tree_warnings:
            if warning not in manifest.warnings:
                manifest.warnings.append(warning)
        save_manifest(ws, manifest)
    return tree


def _write_linkage(ws: OutputWorkspace, outline: OutlineTree, chunks: list[ContentChunk], outline_source: str) -> LinkageFile:
    if not ws.document_tree_path.exists():
        raise WorkspaceError("document_tree.json required for linkage")
    document_tree = DocumentTreeFile.model_validate_json(ws.document_tree_path.read_text(encoding="utf-8"))
    result = build_linkage(
        outline,
        document_tree,
        chunks,
        outline_source=outline_source,
        collect_warnings=True,
    )
    linkage, linkage_warnings = result  # type: ignore[misc]
    ws.linkage_path.write_text(linkage.model_dump_json(indent=2), encoding="utf-8")
    if ws.manifest_path.exists():
        manifest = load_manifest(ws.manifest_path)
        manifest.outputs["linkage"] = "linkage.json"
        for warning in linkage_warnings:
            if warning not in manifest.warnings:
                manifest.warnings.append(warning)
        save_manifest(ws, manifest)
    return linkage


def _populate_chunk_index_tree_nodes(index: ChunkIndex, linkage: LinkageFile) -> list[str]:
    warnings: list[str] = []
    by_outline = {entry.outline_node_id: entry for entry in linkage.entries}
    updated: list[ChunkIndexEntry] = []
    for entry in index.chunks:
        if entry.heading_level is None:
            updated.append(entry)
            continue
        outline_id = entry.primary_outline_node_id or (
            entry.original_node_ids[0] if entry.original_node_ids else None
        )
        if not outline_id:
            updated.append(entry)
            continue
        link = by_outline.get(outline_id)
        if not link or not link.document_tree_node_ids:
            updated.append(entry)
            continue
        expected = link.document_tree_node_ids[0]
        if entry.document_tree_node_id and entry.document_tree_node_id != expected:
            warnings.append(f"chunk_tree_node_mismatch:{entry.chunk_id}")
        updated.append(entry.model_copy(update={"document_tree_node_id": expected}))
    index.chunks = updated
    return warnings


def _append_manifest_warnings(ws: OutputWorkspace, warnings: list[str]) -> None:
    if not warnings or not ws.manifest_path.exists():
        return
    manifest = load_manifest(ws.manifest_path)
    for warning in warnings:
        if warning not in manifest.warnings:
            manifest.warnings.append(warning)
    save_manifest(ws, manifest)


def _safe_progress(
    on_progress: Callable[[str, dict], None] | None,
    stage: str,
    payload: dict,
) -> None:
    if on_progress is None:
        return
    try:
        on_progress(stage, payload)
    except Exception:
        return


def extract_batch(
    input_dir: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
    continue_on_error: bool = True,
) -> PipelineResult:
    manifests: list[Manifest] = []
    errors: list[dict] = []

    source_dir = Path(input_dir)
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    for file_path in sorted(source_dir.iterdir()):
        if not file_path.is_file():
            continue
        try:
            manifest = extract_file(
                file_path,
                out_root / file_path.stem,
                overwrite=overwrite,
            )
            manifests.append(manifest)
        except Exception as exc:
            errors.append({"path": str(file_path), "error": str(exc)})
            if not continue_on_error:
                return PipelineResult(status="failed", manifests=manifests, errors=errors)

    if manifests and not errors:
        status = "success"
    elif manifests and errors:
        status = "partial_success"
    else:
        status = "failed"
    return PipelineResult(status=status, manifests=manifests, errors=errors)


def extract_outline(workspace: Path) -> OutlineTree:
    ws = OutputWorkspace.open_existing(Path(workspace))
    source_path = ws.root
    manifest: Manifest | None = None
    if ws.manifest_path.exists():
        manifest = load_manifest(ws.manifest_path)
        source_path = Path(manifest.source.path)

    tree = build_outline_from_workspace(ws, source_path)

    if manifest is not None:
        manifest.stages["outline"] = StageStatus(status="success")
        manifest.outputs["outline"] = "outline.json"
        save_manifest(ws, manifest)
    return tree


def get_refine_session(workspace: Path) -> RefineSession:
    ws = OutputWorkspace.open_existing(Path(workspace))
    key = str(ws.root.resolve())
    existing = _REFINE_SESSIONS.get(key)
    if existing is not None:
        return existing

    if not ws.outline_path.exists():
        raise WorkspaceError(f"outline.json not found: {ws.outline_path}")
    original_outline = OutlineTree.model_validate(json.loads(ws.outline_path.read_text(encoding="utf-8")))
    session = RefineSession(workspace=ws.root, original_outline=original_outline)
    _REFINE_SESSIONS[key] = session
    return session


def refine_outline(
    workspace: Path,
    instruction: str,
    *,
    session: RefineSession | None = None,
    strict: bool = True,
    llm_client: LLMClient | None = None,
):
    current_session = session or get_refine_session(workspace)
    if current_session.status != "active":
        raise ValidationError("refine session is not active, please reset before refining again")
    if not instruction.strip():
        raise ValidationError("instruction cannot be empty")

    client = llm_client
    if client is None:
        client = create_llm_client_from_env()

    engine = OutlineRefineEngine(llm_client=client, strict=strict, max_retries=2)
    refined, mapping, summary, preview = engine.run_round(session=current_session, instruction=instruction)

    current_session.current_refined = refined
    current_session.current_mapping = mapping
    current_session.instruction_history.append(instruction)
    current_session.round_summaries.append(summary)
    return preview


def accept_refined_outline(
    workspace: Path,
    *,
    session: RefineSession | None = None,
) -> Manifest:
    ws = OutputWorkspace.open_existing(Path(workspace))
    current_session = session or get_refine_session(workspace)
    if current_session.status != "active":
        raise ValidationError("only active refine session can be accepted")
    if current_session.current_refined is None or current_session.current_mapping is None:
        raise ValidationError("no refined outline preview to accept")

    summary = current_session.round_summaries[-1] if current_session.round_summaries else "outline refined"
    persist_refined_artifacts(
        ws,
        refined_outline=current_session.current_refined,
        mapping=current_session.current_mapping,
        summary=summary,
    )
    current_session.status = "accepted"

    if not ws.manifest_path.exists():
        raise WorkspaceError(f"manifest.json not found: {ws.manifest_path}")
    manifest = load_manifest(ws.manifest_path)
    manifest.stages["outline_refine"] = StageStatus(status="success")
    manifest.outputs["outline_refined"] = "outline_refined.json"
    manifest.outputs["outline_mapping"] = "outline_mapping.json"
    manifest.outputs["outline_refine_summary"] = "outline_refine_summary.md"
    save_manifest(ws, manifest)
    return manifest


def discard_refined_outline(workspace: Path, *, session: RefineSession | None = None) -> None:
    current_session = session or get_refine_session(workspace)
    if current_session.status != "active":
        raise ValidationError("only active refine session can be discarded")
    current_session.status = "discarded"
    current_session.current_refined = None
    current_session.current_mapping = None


def reset_refined_outline(workspace: Path, *, force: bool = False) -> RefineSession:
    ws = OutputWorkspace.open_existing(Path(workspace))
    if not ws.outline_path.exists():
        raise WorkspaceError(f"outline.json not found: {ws.outline_path}")

    has_refined_artifacts = ws.outline_refined_path.exists() or ws.outline_mapping_path.exists()
    if has_refined_artifacts and not force:
        raise WorkspaceError("refined artifacts exist, use force=True to reset")

    clear_refined_artifacts(ws)
    original_outline = OutlineTree.model_validate(json.loads(ws.outline_path.read_text(encoding="utf-8")))
    new_session = RefineSession(workspace=ws.root, original_outline=original_outline)
    _REFINE_SESSIONS[str(ws.root.resolve())] = new_session
    return new_session


def discard(workspace: Path, *, session: RefineSession | None = None) -> None:
    discard_refined_outline(workspace, session=session)


def reset(workspace: Path, *, force: bool = False) -> RefineSession:
    return reset_refined_outline(workspace, force=force)


def chunk_document(
    workspace: Path,
    *,
    max_tokens: int = 20_000,
    use_refined: bool = True,
    markdown_headings_only: bool = False,
    on_progress: Callable[[str, dict], None] | None = None,
) -> ChunkIndex:
    ws = OutputWorkspace.open_existing(Path(workspace))
    content_md = ws.content_path.read_text(encoding="utf-8")

    outline_source = "original"
    chunks: list[ContentChunk] = []
    outline_tree: OutlineTree | None = None
    if use_refined and ws.outline_refined_path.exists() and ws.outline_mapping_path.exists():
        outline_source = "refined"
        refined_tree = OutlineTree.model_validate(json.loads(ws.outline_refined_path.read_text(encoding="utf-8")))
        mapping_file = OutlineMappingFile.model_validate(json.loads(ws.outline_mapping_path.read_text(encoding="utf-8")))
        chunks = plan_chunks_from_refined(content_md, refined_tree, mapping_file, max_tokens=max_tokens)
    else:
        outline_tree = OutlineTree.model_validate(json.loads(ws.outline_path.read_text(encoding="utf-8")))
        chunks = plan_chunks(
            content_md,
            outline_tree,
            max_tokens=max_tokens,
            markdown_headings_only=markdown_headings_only,
        )
        for chunk in chunks:
            chunk.outline_source = "original"  # type: ignore[assignment]

    total = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        _safe_progress(
            on_progress,
            "chunk",
            {"message": f"writing chunk {idx}/{total}", "current": idx, "total": total},
        )

    index = write_chunks(chunks, ws.chunks_dir, outline_source=outline_source)

    if outline_tree is not None:
        if not ws.document_tree_path.exists():
            build_tree(ws.root)
        linkage = _write_linkage(ws, outline_tree, chunks, outline_source)
        index_warnings = _populate_chunk_index_tree_nodes(index, linkage)
        index_path = ws.chunks_dir / "index.json"
        index_path.write_text(
            json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _append_manifest_warnings(ws, index_warnings)

    if ws.manifest_path.exists():
        manifest = load_manifest(ws.manifest_path)
        manifest.stages["chunk"] = StageStatus(status="success")
        manifest.outputs["chunks"] = "chunks"
        save_manifest(ws, manifest)
    return index


def enrich_chunks(
    workspace: Path,
    *,
    enable_llm_description: bool = True,
    classification_config: Path | None = None,
    llm_client: LLMClient | None = None,
) -> ChunkIndex:
    ws = OutputWorkspace.open_existing(Path(workspace))
    index_path = ws.chunks_dir / "index.json"
    if not index_path.exists():
        raise WorkspaceError(f"chunks index not found: {index_path}")

    index = ChunkIndex.model_validate(json.loads(index_path.read_text(encoding="utf-8")))
    client = llm_client
    if (enable_llm_description or llm_client is None) and client is None:
        try:
            client = create_llm_client_from_env() if enable_llm_description else None
        except LLMUnavailableError:
            if enable_llm_description:
                raise
            client = None

    for entry in index.chunks:
        chunk_path = ws.chunks_dir / entry.path
        chunk_data = json.loads(chunk_path.read_text(encoding="utf-8"))
        chunk = ContentChunk.model_validate(chunk_data)
        classification = classify_chunk(
            title=chunk.title,
            markdown=chunk.markdown,
            llm_client=client,
            classification_config=classification_config,
        )
        for key, value in classification.items():
            setattr(chunk.metadata, key, value)

        if enable_llm_description:
            description = describe_chunk(title=chunk.title, markdown=chunk.markdown, llm_client=client)
            if description:
                chunk.metadata.description = description
        chunk.metadata.generated_at = datetime.now(UTC).isoformat()
        chunk_path.write_text(
            json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if ws.manifest_path.exists():
        manifest = load_manifest(ws.manifest_path)
        manifest.stages["enrich"] = StageStatus(status="success")
        manifest.outputs["enriched_chunks"] = "chunks"
        save_manifest(ws, manifest)
    return index


def _run_single_pipeline(
    input_path: Path,
    output_dir: Path,
    *,
    overwrite: bool,
    skip_refine: bool,
    skip_enrich: bool,
    refine_instruction: str | None,
    max_tokens: int,
    on_progress: Callable[[str, dict], None] | None,
) -> Manifest:
    _safe_progress(on_progress, "extract", {"message": "extracting document", "current": 0, "total": 1, "input": str(input_path), "output": str(output_dir)})
    manifest = extract_file(input_path, output_dir, overwrite=overwrite)
    _safe_progress(on_progress, "outline", {"message": "building outline", "current": 0, "total": 1, "workspace": str(output_dir)})
    extract_outline(output_dir)
    _safe_progress(on_progress, "tree", {"message": "building document tree", "current": 0, "total": 1, "workspace": str(output_dir)})
    build_tree(output_dir)

    if not skip_refine and refine_instruction:
        _safe_progress(on_progress, "outline_refine", {"message": "refining outline", "workspace": str(output_dir)})
        refine_outline(output_dir, refine_instruction)
        manifest = accept_refined_outline(output_dir)

    chunk_document(
        output_dir,
        max_tokens=max_tokens,
        use_refined=not skip_refine,
        on_progress=on_progress,
    )

    if not skip_enrich:
        _safe_progress(on_progress, "enrich", {"message": "enriching chunks", "workspace": str(output_dir)})
        enrich_chunks(output_dir, enable_llm_description=False)
    return manifest


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
    skip_refine: bool = True,
    skip_enrich: bool = False,
    refine_instruction: str | None = None,
    max_tokens: int = 20_000,
    on_progress: Callable[[str, dict], None] | None = None,
    continue_on_error: bool = True,
) -> PipelineResult:
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if input_path.is_dir():
        manifests: list[Manifest] = []
        errors: list[dict] = []
        output_dir.mkdir(parents=True, exist_ok=True)
        for file_path in sorted(input_path.iterdir()):
            if not file_path.is_file():
                continue
            try:
                manifest = _run_single_pipeline(
                    file_path,
                    output_dir / file_path.stem,
                    overwrite=overwrite,
                    skip_refine=skip_refine,
                    skip_enrich=skip_enrich,
                    refine_instruction=refine_instruction,
                    max_tokens=max_tokens,
                    on_progress=on_progress,
                )
                manifests.append(manifest)
            except Exception as exc:
                errors.append({"path": str(file_path), "error": str(exc)})
                if not continue_on_error:
                    return PipelineResult(status="failed", manifests=manifests, errors=errors)
        if manifests and not errors:
            return PipelineResult(status="success", manifests=manifests, errors=errors)
        if manifests and errors:
            return PipelineResult(status="partial_success", manifests=manifests, errors=errors)
        return PipelineResult(status="failed", manifests=manifests, errors=errors)

    try:
        manifest = _run_single_pipeline(
            input_path,
            output_dir,
            overwrite=overwrite,
            skip_refine=skip_refine,
            skip_enrich=skip_enrich,
            refine_instruction=refine_instruction,
            max_tokens=max_tokens,
            on_progress=on_progress,
        )
    except Exception as exc:
        return PipelineResult(status="failed", manifests=[], errors=[{"path": str(input_path), "error": str(exc)}])
    return PipelineResult(status="success", manifests=[manifest], errors=[])
