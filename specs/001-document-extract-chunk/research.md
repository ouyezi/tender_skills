# Research: 文档提取与智能分块脚本包

**Feature**: `001-document-extract-chunk`  
**Date**: 2026-06-15

## R1: 包名与分发形态

**Decision**: Python 包名 `doc_chunk`，console script `doc-chunk`，模块路径 `src/doc_chunk/`。

**Rationale**: 简短、语义明确；与 tender-doctor 命名风格一致；便于 `pip install -e .` 后在 skills 中 `from doc_chunk import api`。

**Alternatives considered**:
- `tender_doc_tools` — 过长，绑定业务域
- 单体 scripts/ — 不符合 FR-001 可安装库要求

---

## R2: 参考代码移植策略

**Decision**: 从 `tender_doctor` 和 `tender_knowledge` **复制并精简**核心算法，不添加为 pip 依赖。

**Rationale**: 规格明确要求独立运行；两仓库算法成熟但耦合各自应用层。

**Source mapping**:

| 能力 | 参考源 | 移植目标 |
|------|--------|----------|
| PDF/DOCX 提取 | `tender_doctor/extraction/extractors.py`, `renderers.py` | `doc_chunk/extract/`（去除 OCR/vision） |
| 工作区布局 | `tender_doctor/extraction/workspace.py`, `manifest.py` | `doc_chunk/workspace/` |
| 分块 | `tender_doctor/extraction/chunking.py` | `doc_chunk/chunk/`（扩展 8 级） |
| DOCX TOC | `tender_knowledge/.../docx_toc_extractor.py` 等 | `doc_chunk/outline/` |
| 块分类 | `tender_knowledge/.../chunk_classification_service.py` | `doc_chunk/metadata/classify.py`（去 DB） |

**Alternatives considered**:
- Git submodule — 增加消费方复杂度
- 直接 depend tender_doctor — 违反 FR-001

---

## R3: Word 解析技术栈

**Decision**: `python-docx` 读段落/样式；`lxml` 直接解析 `document.xml` 提取 TOC 字段（与 tender_knowledge 一致）。

**Rationale**: TOC 字段解析需 lxml；python-docx 足够处理正文与图片关系。

**Alternatives considered**:
- 仅 python-docx — 无法可靠读 TOC 字段
- Pandoc — 外部二进制依赖，不利于 skills 部署

---

## R4: PDF 解析技术栈

**Decision**: `pymupdf` (fitz) 提取文本、书签 TOC、嵌入图片；扫描页导出为图片写入 `images/`。

**Rationale**: tender_doctor 已验证；书签即 PDF 目录树来源。

**Alternatives considered**:
- pdfplumber — 书签与图片导出较弱
- 提取阶段 OCR — 规格明确排除（Out of Scope）

---

## R5: 数据模型与 Schema 版本化

**Decision**: Pydantic v2 模型 + 顶层 `schema_version: Literal["1.0"]`；契约测试用 `model_json_schema()` 导出。

**Rationale**: 类型安全、与 Python API 一体；FR-012 要求稳定可版本化 JSON。

**Alternatives considered**:
- 手写 JSON Schema — 双份维护
- dataclasses only — 无运行时校验

---

## R6: LLM 集成

**Decision**: `LLMClient` Protocol：`complete(messages, *, response_format="json") -> str`；默认 OpenAI-compatible（`OPENAI_API_BASE` + `OPENAI_API_KEY`）；可选 dashscope 适配器。

**Rationale**: 目录树优化与元数据增强均需 JSON 输出；与 tender 项目常见配置兼容。

**Alternatives considered**:
- 硬编码 dashscope — 灵活性差
- LangChain — 过重，YAGNI

---

## R7: 目录树优化实现

**Decision**: 端到端 LLM 输出 `{outline_refined, node_mappings, change_summary}` + `OutlineMappingValidator`；失败重试 ≤2 次；session 内存态，`accept` 落盘。

**Rationale**: 已批准完整需求 `2026-06-15-doc-chunk-requirements.md` §6；自然语言指令灵活性高。

**Alternatives considered**:
- 操作列表 DSL — 用户体验差（brainstorming 已否决）

---

## R8: 分块 token 估算

**Decision**: 复用 tender_doctor 启发式：`len(text) // 4` 或按字符切分 `max_tokens * 4`；默认 `max_tokens=20000`。

**Rationale**: 与参考实现一致；规格 FR-007a 明确默认值。

**Alternatives considered**:
- tiktoken — 更准但增加依赖与模型绑定
- 字符数 — 与 tender_doctor 不对齐

---

## R9: CLI 框架

**Decision**: `typer` 子命令结构，退出码枚举：0 成功、1 失败、2 部分成功、3 参数错误、4 不支持格式。

**Rationale**: 类型友好、与 FastAPI 生态一致；FR-014 要求区分退出码。

**Alternatives considered**:
- argparse — 冗长
- click — 亦可，typer 文档更佳

---

## R10: 测试夹具策略

**Decision**: `tests/fixtures/` 内置最小 synthetic docx/pdf；集成测试可选引用 `../tender_doctor` 样例（pytest marker `external_samples`，CI 默认跳过）。

**Rationale**: 仓库自包含；仍可验证真实标书样例。

**Alternatives considered**:
- 仅外部样例 — CI 不稳定
- 全复制标书 — 体积大、版权

---

## R11: 分类配置格式

**Decision**: `classification.yaml`：

```yaml
knowledge_types:
  - id: scheme
    keywords: ["方案", "服务", "实施"]
custom_tags:
  - id: legal_clause
    keywords: ["条款", "合规"]
```

内置枚举硬编码于 `metadata/classify.py`；YAML 仅扩展。

**Rationale**: FR-010 内置 + 可扩展；无 DB 依赖。

---

## R12: 严格模式默认值（映射校验）

**Decision**: `OutlineMappingValidator` 默认 **strict=True**（合并范围不连续则阻止 accept）；CLI/API 可 `--lenient` 降级为警告。

**Rationale**: 规格 Edge Case「严格模式阻止 accept」；默认保证分块质量。

**Alternatives considered**:
- 默认宽松 — 易产出错误分块

---

## Resolved NEEDS CLARIFICATION

所有 Technical Context 未知项已通过上述决策解决，无遗留 NEEDS CLARIFICATION。
