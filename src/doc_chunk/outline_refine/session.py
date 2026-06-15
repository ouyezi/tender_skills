from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from doc_chunk.models.outline import OutlineMappingFile, OutlineTree


@dataclass
class RefineSession:
    workspace: Path
    original_outline: OutlineTree
    current_refined: OutlineTree | None = None
    current_mapping: OutlineMappingFile | None = None
    instruction_history: list[str] = field(default_factory=list)
    round_summaries: list[str] = field(default_factory=list)
    status: Literal["active", "accepted", "discarded"] = "active"

    def base_outline(self) -> OutlineTree:
        return self.current_refined or self.original_outline
