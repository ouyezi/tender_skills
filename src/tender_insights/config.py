from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class InsightsConfig:
    llm_model: str = "qwen-plus"
    max_retries: int = 2
    chunks_per_batch: int = 3

    @classmethod
    def from_env(cls) -> InsightsConfig:
        provider = (os.environ.get("LLM_PROVIDER") or "qwen").lower()
        default_model = "qwen-plus" if provider == "qwen" else "gpt-4o-mini"
        return cls(
            llm_model=(
                os.environ.get("LLM_MODEL")
                or os.environ.get("DOC_CHUNK_LLM_MODEL")
                or default_model
            ),
        )
