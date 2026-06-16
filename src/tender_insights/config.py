from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class InsightsConfig:
    llm_model: str = "gpt-4o-mini"
    max_retries: int = 2
    chunks_per_batch: int = 3

    @classmethod
    def from_env(cls) -> InsightsConfig:
        return cls(
            llm_model=os.environ.get("DOC_CHUNK_LLM_MODEL", "gpt-4o-mini"),
        )
