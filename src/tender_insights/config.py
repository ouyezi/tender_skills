from __future__ import annotations

from dataclasses import dataclass
import os


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return int(raw)


@dataclass(frozen=True, slots=True)
class InsightsConfig:
    llm_model: str = "qwen3.7-max"
    max_retries: int = 2
    ocr_enabled: bool = True
    ocr_model: str = "qwen-vl-ocr"
    segment_min_tokens: int = 2000
    segment_max_tokens: int = 12000
    segment_keyword_match_enabled: bool = False
    ocr_logo_max_bytes: int = 10240
    ocr_logo_max_px: int = 128
    ocr_max_long_edge: int = 1500
    brief_chunk_char_limit: int = 20000
    brief_summary_max_chars: int = 500
    gen_catalog_excerpt_max_chars: int = 2000
    gen_catalog_excerpt_min_chars: int = 200

    @classmethod
    def from_env(cls) -> InsightsConfig:
        provider = (os.environ.get("LLM_PROVIDER") or "qwen").lower()
        default_model = "qwen3.7-max" if provider == "qwen" else "gpt-4o-mini"
        return cls(
            llm_model=(
                os.environ.get("LLM_MODEL")
                or os.environ.get("DOC_CHUNK_LLM_MODEL")
                or default_model
            ),
            ocr_enabled=_env_bool("OCR_ENABLED", True),
            ocr_model=os.environ.get("OCR_MODEL") or "qwen-vl-ocr",
            segment_min_tokens=_env_int("SEGMENT_MIN_TOKENS", 2000),
            segment_max_tokens=_env_int("SEGMENT_MAX_TOKENS", 12000),
            segment_keyword_match_enabled=_env_bool("INTERPRET_SEGMENT_KEYWORD_MATCH", False),
            ocr_logo_max_bytes=_env_int("OCR_LOGO_MAX_BYTES", 10240),
            ocr_logo_max_px=_env_int("OCR_LOGO_MAX_PX", 128),
            ocr_max_long_edge=_env_int("OCR_MAX_LONG_EDGE", 1500),
            brief_chunk_char_limit=_env_int("BRIEF_CHUNK_CHAR_LIMIT", 20000),
            brief_summary_max_chars=_env_int("BRIEF_SUMMARY_MAX_CHARS", 500),
            gen_catalog_excerpt_max_chars=_env_int("GEN_CATALOG_EXCERPT_MAX_CHARS", 2000),
            gen_catalog_excerpt_min_chars=_env_int("GEN_CATALOG_EXCERPT_MIN_CHARS", 200),
        )
