# Python API Contract: doc_chunk

**Module**: `doc_chunk.api`  
**Date**: 2026-06-15

## Design Principles

- 所有函数接受 `Path` 类型路径参数
- 返回 pydantic 模型或 `Result` 对象，不抛裸异常给 skills（内部异常包装为 `DocChunkError` 层次）
- CLI 为薄封装，直接调用本模块

---

## Types (public)

```python
from pathlib import Path
from doc_chunk.models.manifest import Manifest, PipelineResult
from doc_chunk.models.outline import OutlineTree, RefinePreview
from doc_chunk.models.chunk import ChunkIndex
from doc_chunk.outline_refine.session import RefineSession

class DocChunkError(Exception): ...
class UnsupportedFormatError(DocChunkError): ...
class WorkspaceError(DocChunkError): ...
class LLMUnavailableError(DocChunkError): ...
class ValidationError(DocChunkError): ...
```

---

## Extraction

```python
def extract_file(
    input_path: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> Manifest:
    """提取单文件到 output_dir 工作区。"""
```

```python
def extract_batch(
    input_dir: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
    continue_on_error: bool = True,
) -> PipelineResult:
    """批量提取；默认 continue_on_error=True。"""
```

---

## Outline

```python
def extract_outline(workspace: Path) -> OutlineTree:
    """从工作区 content.md 生成 outline.json 并返回树。"""
```

---

## Outline Refine

```python
def get_refine_session(workspace: Path) -> RefineSession:
    """获取或创建 active session。"""

def refine_outline(
    workspace: Path,
    instruction: str,
    *,
    session: RefineSession | None = None,
    strict: bool = True,
    llm_client: LLMClient | None = None,
) -> RefinePreview:
    """
    执行一轮 LLM 优化。
    成功时更新 session.current_refined；失败保留上轮树。
    最多自动重试 2 次。
    """

def accept_refined_outline(
    workspace: Path,
    *,
    session: RefineSession | None = None,
) -> Manifest:
    """落盘 refined 产物，锁定 session。"""

def discard_refined_outline(workspace: Path, *, session: RefineSession | None = None) -> None:

def reset_refined_outline(workspace: Path, *, force: bool = False) -> RefineSession:
    """清除已 accept 产物，新建 session。"""
```

### RefinePreview

| Field | Type |
|-------|------|
| node_count_before | int |
| node_count_after | int |
| change_summary | str |
| warnings | list[str] |
| title_diff | list[str] |
| validation_passed | bool |
| validation_errors | list[str] |

---

## Chunking

```python
def chunk_document(
    workspace: Path,
    *,
    max_tokens: int = 20_000,
    use_refined: bool = True,
) -> ChunkIndex:
    """
    分块并写入 chunks/。
    use_refined=True 时若 outline_refined.json 存在则优先使用。
    """
```

---

## Metadata Enrichment

```python
def enrich_chunks(
    workspace: Path,
    *,
    enable_llm_description: bool = True,
    classification_config: Path | None = None,
    llm_client: LLMClient | None = None,
) -> ChunkIndex:
    """为已有 chunks 添加描述与分类元数据。"""
```

---

## Pipeline

```python
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
) -> PipelineResult:
    """
    端到端流水线。
    refine_instruction 非空时执行单轮 refine + accept。
    on_progress(stage_id, payload) 用于 skills 进度汇报。
    """
```

### PipelineResult

| Field | Type |
|-------|------|
| status | `success` \| `partial_success` \| `failed` |
| manifests | list[Manifest] |
| errors | list[dict] |

---

## LLMClient Protocol

```python
class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: Literal["text", "json"] = "text",
        timeout: float = 60.0,
    ) -> str: ...
```

工厂：

```python
def create_llm_client_from_env() -> LLMClient:
    """读取 OPENAI_API_KEY / OPENAI_API_BASE / DOC_CHUNK_LLM_MODEL。"""
```

---

## Skills Integration Example

```python
from pathlib import Path
from doc_chunk.api import (
    extract_file,
    extract_outline,
    refine_outline,
    accept_refined_outline,
    chunk_document,
    enrich_chunks,
)

workspace = Path("output/bid-doc")

extract_file("input/bid.docx", workspace)
extract_outline(workspace)

preview = refine_outline(workspace, "合并所有资质相关章节")
if preview.validation_passed:
    accept_refined_outline(workspace)

chunk_document(workspace, use_refined=True)
enrich_chunks(workspace)
```

---

## Versioning

- 公共 API 遵循 semver
- JSON `schema_version` 变更时提供迁移说明，API 保持向后兼容读取旧工作区
