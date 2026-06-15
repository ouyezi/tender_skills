from pydantic import BaseModel, Field


class ChunkConfig(BaseModel):
    max_tokens: int = Field(default=20_000, ge=1)


class LLMConfig(BaseModel):
    model: str = "gpt-4o-mini"
    timeout_seconds: float = 60.0
    max_retries: int = 2


class RefineConfig(BaseModel):
    strict_validation: bool = True
