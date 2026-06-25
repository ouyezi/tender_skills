from __future__ import annotations

from dataclasses import dataclass, field

from doc_chunk.workspace.layout import OutputWorkspace
from tender_insights.brief.models import TenderBriefFile
from tender_insights.interpret.models import InterpretationFile
from tender_insights.template.models import TemplatesIndexFile


@dataclass(slots=True)
class PrerequisiteReport:
    interpretation: InterpretationFile
    brief: TenderBriefFile | None = None
    templates: TemplatesIndexFile | None = None
    warnings: list[str] = field(default_factory=list)


def validate_prerequisites(
    workspace: OutputWorkspace,
    *,
    overwrite: bool = False,
) -> PrerequisiteReport:
    interpretation_path = workspace.root / "interpretation.json"
    if not interpretation_path.is_file():
        raise FileNotFoundError(f"interpretation.json not found in {workspace.root}")

    interpretation = InterpretationFile.model_validate_json(
        interpretation_path.read_text(encoding="utf-8")
    )
    if not interpretation.directory_requirements and not interpretation.directory_outline.nodes:
        raise ValueError("interpretation has no directory requirements or outline nodes")

    accepted = workspace.root / "bid_outline.json"
    if accepted.is_file() and not overwrite:
        raise FileExistsError("bid_outline.json already exists; pass overwrite=True")

    warnings: list[str] = []
    brief = None
    brief_path = workspace.root / "tender_brief.json"
    if brief_path.is_file():
        brief = TenderBriefFile.model_validate_json(brief_path.read_text(encoding="utf-8"))
    else:
        warnings.append("tender_brief.json missing; continuing without brief snapshot")

    templates = None
    templates_path = workspace.root / "templates" / "index.json"
    if templates_path.is_file():
        templates = TemplatesIndexFile.model_validate_json(templates_path.read_text(encoding="utf-8"))
    else:
        warnings.append("templates/index.json missing; template_ref will remain null")

    return PrerequisiteReport(
        interpretation=interpretation,
        brief=brief,
        templates=templates,
        warnings=warnings,
    )
