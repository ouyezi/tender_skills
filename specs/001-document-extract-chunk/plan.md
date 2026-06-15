# Implementation Plan: 文档提取与智能分块脚本包

**Branch**: `001-document-extract-chunk` | **Date**: 2026-06-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-document-extract-chunk/spec.md`  
**完整需求**: [`docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md`](../../docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md)

## Summary

构建独立 Python 包 `doc_chunk`，提供 CLI + 库 API，实现 Word/PDF 文档提取 → 目录树生成 → 可选 LLM 目录树优化 → 语义分块 → 元数据增强五阶段流水线。行为对齐 `tender_doctor` 提取管线与 `tender_knowledge` 目录树策略，但不耦合其运行时。输出稳定 JSON/Markdown 工作区，供 tender_skills 消费。

## Technical Context

**Language/Version**: Python 3.11+（与 tender_doctor `>=3.11.8` 对齐）

**Primary Dependencies**:
- `python-docx` + `lxml` — Word 解析、TOC/标题推断（参考 tender_knowledge）
- `pymupdf` (fitz) — PDF 文本、书签、图片导出（参考 tender_doctor）
- `pydantic` v2 — 数据模型与 JSON schema 校验
- `pyyaml` — 分类规则与配置
- `typer` — CLI
- `jsonschema` — 契约测试
- LLM：`openai` 兼容客户端 + 可选 `dashscope`（与现有项目 LLM 配置一致）

**Storage**: 文件系统工作区（`content.md`、`images/`、`outline*.json`、`chunks/`、`manifest.json`）；无数据库

**Testing**: `pytest`；单元 / 契约 / 集成三层；夹具来自 tender_doctor/tender_knowledge 样例文档

**Target Platform**: macOS / Linux CLI；skills 内 Python import

**Project Type**: 独立 Python 库 + CLI

**Performance Goals**: 50 页文档端到端（不含 LLM）< 3 分钟（SC-005）

**Constraints**:
- 不依赖 tender_doctor / tender_knowledge 包
- 提取阶段无 LLM、无图片 OCR
- 目录树 1–8 级；默认 chunk max 20,000 token
- 批量默认 continue-on-error

**Scale/Scope**: 单文档数百页；批量目录处理；5 个流水线阶段

## Constitution Check

*GATE: Constitution 模板未定制，采用 Spec Kit 默认原则：*

| 原则 | 状态 | 说明 |
|------|------|------|
| Library-First | ✅ PASS | 核心逻辑在 `doc_chunk` 包，CLI 薄封装 |
| CLI Interface | ✅ PASS | `typer` 子命令：extract / outline / refine / chunk / enrich / pipeline |
| Test-First | ✅ PASS | 契约测试锁定 JSON schema；实现前编写失败测试 |
| Integration Testing | ✅ PASS | 端到端工作区夹具 + 样例文档 |
| Simplicity | ✅ PASS | 单包结构；LLM 可插拔；无 Web 层 |

**Post-Design Re-check**: ✅ 无违规；outline-refine session 内存态不引入额外服务

## Project Structure

### Documentation (this feature)

```text
specs/001-document-extract-chunk/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md
│   ├── python-api.md
│   └── workspace-schemas.md
└── tasks.md              # /speckit-tasks 输出
```

### Source Code (repository root)

```text
pyproject.toml
README.md
src/doc_chunk/
├── __init__.py              # 公共 API 重导出
├── api.py                   # extract_file, extract_outline, refine_outline, chunk, enrich, run_pipeline
├── cli/
│   └── main.py              # typer 入口：doc-chunk
├── config.py                # ChunkConfig, LLMConfig, ClassificationConfig
├── models/                  # pydantic 实体
│   ├── document.py
│   ├── outline.py
│   ├── chunk.py
│   └── manifest.py
├── workspace/               # OutputWorkspace 布局与 manifest 读写
├── extract/                 # Word/PDF → content.md + images/
│   ├── docx_extractor.py
│   ├── pdf_extractor.py
│   └── renderer.py
├── outline/                 # outline.json 多策略提取
│   ├── toc_extractor.py     # 移植 tender_knowledge 策略链
│   ├── hierarchy.py
│   └── builder.py
├── outline_refine/          # LLM 多轮优化
│   ├── session.py
│   ├── engine.py
│   ├── validator.py
│   └── preview.py
├── chunk/                   # 分块 + refined 映射
│   ├── planner.py
│   ├── refined_planner.py
│   └── tokenizer.py
├── metadata/                # 描述 + 分类
│   ├── describe.py
│   └── classify.py
└── llm/                     # 抽象客户端
    ├── client.py
    └── prompts/

tests/
├── unit/
├── contract/
├── integration/
└── fixtures/                # 最小 docx/pdf + 期望 JSON 片段
```

**Structure Decision**: 单包 `doc_chunk`，按流水线阶段划分子模块；`api.py` 为 skills 稳定入口，`cli/` 调用同一服务层。

## Phase 0: Research Summary

详见 [research.md](./research.md)。关键决策：

1. **移植而非依赖** — 从 tender_doctor/tender_knowledge 复制并精简算法，避免包耦合
2. **Pydantic 模型即 Schema** — `schema_version` 字段 + jsonschema 导出用于契约测试
3. **LLM 抽象** — `LLMClient` 协议；默认 OpenAI-compatible；环境变量配置
4. **工作区布局** — 对齐 tender_doctor `OutputWorkspace`，扩展 outline_refine 产物
5. **分块双路径** — `ChunkPlanner`（原始树）+ `RefinedChunkPlanner`（优化树+mapping）

## Phase 1: Design Artifacts

| 产物 | 路径 |
|------|------|
| 数据模型 | [data-model.md](./data-model.md) |
| CLI 契约 | [contracts/cli.md](./contracts/cli.md) |
| Python API 契约 | [contracts/python-api.md](./contracts/python-api.md) |
| 工作区 JSON Schema | [contracts/workspace-schemas.md](./contracts/workspace-schemas.md) |
| 验证指南 | [quickstart.md](./quickstart.md) |

## Implementation Phases (for /speckit-tasks)

### Phase A — 脚手架与工作区 (P1 基础)
- pyproject.toml、`doc_chunk` 包骨架、`OutputWorkspace`、`manifest.json` v1
- 契约测试框架 + 空实现冒烟

### Phase B — 文档提取 (User Story 1)
- DOCX/PDF 提取器、Markdown 渲染、图片导出
- `extract` CLI/API；夹具测试 SC-001

### Phase C — 目录树 (User Story 2)
- 多策略 TOC 链（toc → heading → content → flat）
- `outline.json` 输出；8 级层级支持

### Phase D — 分块 (User Story 3 核心)
- `ChunkPlanner`：section path、heading_level、20k token 续切
- `chunks/` 输出；SC-003 对齐测试

### Phase E — 元数据增强 (User Story 3 扩展)
- 规则分类 + LLM 描述/分类；`classification.yaml` 扩展点

### Phase F — 目录树优化 (User Story 4)
- `OutlineRefineSession`、`OutlineRefineEngine`、`OutlineMappingValidator`
- accept 落盘；`RefinedChunkPlanner`；SC-008

### Phase G — 流水线与批量
- `run_pipeline`、批量 continue-on-error、退出码

## Complexity Tracking

> 无 Constitution 违规需豁免。

## Risk & Mitigation

| 风险 | 缓解 |
|------|------|
| 移植代码与上游漂移 | 契约测试 + 标注来源文件 |
| LLM 输出不稳定 | 校验器 + 2 次重试 + 结构化 JSON prompt |
| 合并节点范围空洞 | MappingValidator 严格模式默认开启 |
| 大文档性能 | 流式块索引；进度回调 API |

## Next Step

实现计划（bite-sized TDD 任务）见 [`docs/superpowers/plans/2026-06-15-doc-chunk.md`](../../docs/superpowers/plans/2026-06-15-doc-chunk.md)。

执行 `/speckit-tasks` 可同步生成 `tasks.md` checklist（可选）。
