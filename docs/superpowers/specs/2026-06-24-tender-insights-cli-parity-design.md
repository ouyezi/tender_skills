# tender-insights CLI 与 Viewer 编排对齐设计

**日期:** 2026-06-24  
**状态:** 已批准

## 背景

`tender_insights` 核心解读逻辑已内聚在 `src/tender_insights/`，CLI 入口 `tender-insights` 已存在。但 Viewer 与 CLI 在以下方面不一致：

1. 双文件工作区合并（`workspace_merge`）仅在 Viewer
2. doc_chunk 前置参数不一致（`skip_enrich`）
3. Viewer 绕过 `api.interpret_document`，直接调用 `interpret_workspace`
4. 无可读报告渲染，仅产出 `interpretation.json`

## 目标

- CLI 与 Viewer 共用同一套工作区准备与解读编排
- 支持命令行双文件解读（招标正文 + 技术规范等）
- 新增 Markdown 报告渲染子命令
- 保持现有解读质量与 Viewer 行为等价

## 非目标

- HTML/PDF 报告
- 三文件及以上 merge
- 将 `legal` 并入 `interpret` 流程

## 架构

### 新增模块

| 模块 | 职责 |
|------|------|
| `tender_insights/common/workspace_merge.py` | 双工作区合并（自 Viewer 迁移） |
| `tender_insights/common/pipeline_runner.py` | 统一 pipeline 参数、`prepare_workspaces()` |
| `tender_insights/interpret/render.py` | `interpretation.json` → Markdown |

### API 扩展（`tender_insights/api.py`）

| 函数 | 说明 |
|------|------|
| `prepare_workspaces(paths, output_dir, overwrite)` | 单/多文件工作区准备 |
| `setup_interpret_llm_logging(workspace)` | 设置 `INTERPRET_LOG_JSONL` |
| `run_interpret_job(workspace, *, client, on_progress, include_template)` | logging + interpret + 可选 template |
| `render_interpretation_report(workspace, output_path)` | 读取 JSON 写 Markdown |

### Pipeline 参数

```python
INSIGHTS_PIPELINE_KWARGS = {"skip_refine": True, "skip_enrich": True}
```

`resolve_workspace()` 与 Viewer 均使用此常量。解读阶段 OCR 由 `prepare_interpret_source` 独立完成。

### CLI

```bash
tender-insights interpret bid.docx spec.docx -o ./out --overwrite
tender-insights render ./out -o ./out/interpret_report.md
```

`interpret` / `all` 接受多个 `PATH`；≥2 个原始文件时自动 merge。`template` / `legal` / `render` 仍接受单个工作区。

### Viewer 收敛

`InterpretPipelineService` 调用 `prepare_workspaces` + `run_interpret_job`，删除内联 merge/pipeline 逻辑。进度回调由 Viewer 注入。

### 数据流

```
CLI / Viewer → api.prepare_workspaces → [pipeline × N] → [merge] → api.run_interpret_job → interpretation.json
CLI render → api.render_interpretation_report → interpret_report.md
```

## 错误处理

- 多原始文件未指定 `-o`：`WorkspaceResolveError`
- 超过 2 个原始文件：明确错误提示
- merge 校验失败：`WorkspaceResolveError`
- `render` 无 `interpretation.json`：退出码 1

## 测试

- `tests/tender_insights/unit/test_workspace_merge.py`（自 Viewer 迁移）
- `tests/tender_insights/integration/test_prepare_workspaces.py`
- `tests/tender_insights/unit/test_interpret_render.py`
- `tests/tender_insights/unit/test_cli.py`
- 现有 Viewer interpret 测试保持通过

## 兼容性

- `viewer.services.workspace_merge` 保留 thin re-export
- `skip_enrich` 行为变更：CLI 单文件路径与 Viewer 对齐（`True`）
