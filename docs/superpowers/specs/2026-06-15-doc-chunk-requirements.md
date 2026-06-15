# 完整需求规格：doc_chunk 文档提取与智能分块脚本包

**版本**: 1.0  
**日期**: 2026-06-15  
**状态**: 已批准  
**Feature ID**: `001-document-extract-chunk`  
**实现计划**: [`specs/001-document-extract-chunk/plan.md`](../../../specs/001-document-extract-chunk/plan.md)

---

## 1. 概述与目标

### 1.1 背景

构建独立 Python 包 **`doc_chunk`**（CLI：`doc-chunk`），将 Word/PDF 文档处理为结构化工作区，供 tender_skills 及下游 agent 消费。行为对齐 `tender_doctor` 提取管线与 `tender_knowledge` 目录树策略，**不耦合**其应用运行时。

### 1.2 产品目标

| # | 目标 |
|---|------|
| G1 | 提取文档为 Markdown + 图片子目录 |
| G2 | 自动生成 1–8 级目录树 |
| G3 | 可选 LLM 多轮优化目录树后精准分块 |
| G4 | 块级元数据（描述、分类）增强 |
| G5 | CLI + Python 库 API 双入口，输出稳定 JSON schema |

### 1.3 范围边界

**In Scope (v1)**

- 输入：`.docx`、`.doc`、`.docm`、`.pdf`
- 五阶段流水线：extract → outline → outline-refine（可选）→ chunk → enrich
- 文件系统工作区输出；批量处理；分阶段恢复执行

**Out of Scope (v1)**

- Web UI / 上传流程
- 提取阶段图片 OCR、image_notes、视觉 LLM
- tender_knowledge 数据库写入、tender_doctor 合规诊断
- PPT 深度支持、实时协同编辑

### 1.4 术语表

| 术语 | 定义 |
|------|------|
| 工作区 (Workspace) | 单次文档处理的输出根目录 |
| 目录树 (Outline) | 章节层级 JSON，`outline.json` |
| 优化目录树 (Refined Outline) | LLM accept 后的树，`outline_refined.json` |
| 块 (Chunk) | 按目录语义切分的 Markdown 片段 |
| section path | 从根到当前标题的祖先链，最深 8 级 |
| 续切块 | 超长章节内按 token 限制的后续块，`heading_level=null` |

### 1.5 目标用户

内部开发者与自动化 agent（skills）；主交互为 Python import，辅以为 CLI 与 JSON 工作区。

---

## 2. 用户场景

### US1 — 文档提取 (P1)

**作为**技能开发者，**我希望**输入 Word/PDF 获得 Markdown 与图片目录，**以便**下游直接消费结构化内容。

**独立测试**：仅运行 `extract`，验证 `content.md`、`images/`、`manifest.json`。

| ID | Given | When | Then |
|----|-------|------|------|
| US1-1 | 含标题/表格/图片的 Word | extract | 产出 content.md、images/、manifest |
| US1-2 | 含书签的 PDF | extract | 保留层级与顺序，图片相对路径引用 |
| US1-3 | 扫描页 PDF | extract | 导出页面图，清单警告无文本，不做 OCR |
| US1-4 | 工作区已存在 | extract 无 --overwrite | 拒绝并报错 |

### US2 — 目录树提取 (P2)

**作为**技能开发者，**我希望**获得层级目录树，**以便**作为分块依据。

**独立测试**：运行 `outline`，验证 `outline.json` 节点字段与策略标识。

| ID | Given | When | Then |
|----|-------|------|------|
| US2-1 | Word 含 TOC 字段 | outline | 优先 TOC 策略生成树 |
| US2-2 | 无 TOC 有标题样式 | outline | 启发式推断，低置信标 needs_review |
| US2-3 | PDF 含书签 | outline | 从书签生成树 |
| US2-4 | 无章节结构 | outline | 扁平兜底，标注策略 |
| US2-5 | 5–8 级嵌套标题 | outline + chunk | 每级可独立节点，section path 完整 |

### US3 — 分块与元数据 (P3)

**作为**技能开发者，**我希望**按目录树切块并附加描述与分类，**以便**检索与问答。

**独立测试**：运行 `chunk` + `enrich`，验证块元数据完整性。

| ID | Given | When | Then |
|----|-------|------|------|
| US3-1 | content + outline | chunk | 块含 section_path、heading_level、链接 |
| US3-2 | 章节超 20k token | chunk | 章节内续切，续块继承 path |
| US3-3 | 启用 LLM | enrich | 每块 1–3 句描述 |
| US3-4 | 分类配置 | enrich | 类型建议 + 置信度 + 依据 |
| US3-5 | 封面在首标题前 | chunk | 独立前言块，path=[] |

### US4 — 目录树 LLM 优化 (P2.5)

**作为**技能开发者，**我希望**多轮自然语言调整目录后再分块，**以便**按业务语义合并章节且可追溯原文。

**独立测试**：`refine` → `refine-accept` → `chunk`，验证 refined 映射与块边界。

| ID | Given | When | Then |
|----|-------|------|------|
| US4-1 | outline + 指令 | refine | 预览含映射与校验结果 |
| US4-2 | 预览不满意 | 再次 refine | 增量调整，session 不丢 |
| US4-3 | 满意 | accept | 落盘 refined/mapping/summary |
| US4-4 | 已 accept | chunk | outline_source=refined，含 original_node_ids |
| US4-5 | 校验失败 | 重试后仍失败 | 报错，保留上轮树 |

---

## 3. 功能需求 (FR)

### 3.1 包与集成

| ID | 需求 |
|----|------|
| FR-001 | MUST 为可安装 Python 包 `doc_chunk`，不依赖 tender_doctor/tender_knowledge 运行时 |
| FR-001a | MUST 提供库 API（`doc_chunk.api`）与 CLI（`doc-chunk`），共享核心逻辑 |
| FR-001b | MUST 支持单文件与目录批量处理五阶段能力 |

### 3.2 提取 (extract)

| ID | 需求 |
|----|------|
| FR-002 | MUST 支持 docx/doc/docm/pdf |
| FR-003 | MUST 输出 content.md + images/ 相对路径引用；**禁止**提取阶段 OCR/LLM 图像描述 |
| FR-004 | MUST 生成 manifest.json（源信息、状态、警告、错误） |
| FR-004a | 默认禁止覆盖已有工作区，需 `--overwrite` |

### 3.3 目录树 (outline)

| ID | 需求 |
|----|------|
| FR-005 | MUST 输出 1–8 级层级树；节点含 id、title、level、parent_id、sort_order、anchor、strategy |
| FR-006 | MUST 策略链：TOC/书签 → 标题启发式 → 内容启发式 → 扁平兜底 |

### 3.4 分块 (chunk)

| ID | 需求 |
|----|------|
| FR-007 | MUST 按目录语义边界切分，禁止无依据硬切段落/表格 |
| FR-007a | 章节内续切默认 max **20,000 token**（可配置） |
| FR-008 | 块 MUST 含：chunk_id、title、section_path(≤8)、heading_level、source_ranges、image_refs、prev/next 链接 |
| FR-018 | 存在已 accept 的 refined 树时 MUST 优先按 mapping 范围切分 |
| FR-018a | 块 MUST 含 outline_source、refined_node_id、original_node_ids |

### 3.5 元数据增强 (enrich)

| ID | 需求 |
|----|------|
| FR-009 | MUST 支持 LLM 生成 1–3 句块描述（可关闭） |
| FR-010 | MUST 内置知识类型枚举（scheme/product/qualification/other）+ YAML 扩展自定义标签；规则优先、LLM 补充 |

### 3.6 流水线

| ID | 需求 |
|----|------|
| FR-011 | MUST 支持分阶段执行与 `pipeline` 串联；阶段可基于工作区恢复 |
| FR-011a | 阶段顺序：extract → outline → [outline-refine] → chunk → enrich |

### 3.7 目录树优化 (outline-refine)

| ID | 需求 |
|----|------|
| FR-015 | MUST 接受自然语言 + 原始树 + 当前 refined 树作为 LLM 输入 |
| FR-016 | MUST 支持 merge/split/reparent/rename；节点 MUST 有 source_refs 或 anchor |
| FR-017 | MUST 多轮预览；仅 accept 落盘；不存每轮完整 JSON |
| FR-019 | MUST 确定性校验；失败自动重试 LLM ≤2 次 |

### 3.8 输出与质量

| ID | 需求 |
|----|------|
| FR-012 | 结构化 JSON MUST 含 schema_version: "1.0" |
| FR-013 | MUST 提供 needs_review、token_estimate、warnings 等质量信号 |
| FR-014 | MUST 退出码：0 成功 / 1 失败 / 2 部分成功 / 3 参数错误 / 4 不支持格式 |
| FR-014a | 批量默认 continue-on-error，汇总逐文件结果 |

---

## 4. 非功能需求 (NFR)

| ID | 类别 | 需求 |
|----|------|------|
| NFR-001 | 性能 | 50 页内文档 extract+outline+chunk（无 LLM）< 3 分钟 |
| NFR-002 | 性能 | 数百页文档各阶段进度可回调（`on_progress`） |
| NFR-003 | 可靠性 | 单文件批量失败不阻断其余（默认） |
| NFR-004 | 可靠性 | LLM 超时/限流时 enrich 降级为规则分类并记录警告 |
| NFR-005 | 可维护性 | 从 tender_* 移植代码须标注来源文件 |
| NFR-006 | 可测试性 | 单元/契约/集成三层测试；契约锁定 JSON schema |
| NFR-007 | 可观测性 | logs/ 目录；manifest.stages 记录每阶段状态与时间 |
| NFR-008 | 兼容性 | Python 3.11+；macOS/Linux |
| NFR-009 | 安全性 | API 密钥仅通过环境变量；工作区禁止覆盖系统目录 |
| NFR-010 | 扩展性 | LLM 通过 `LLMClient` 协议可替换；分类通过 YAML 扩展 |

---

## 5. 流水线与阶段

### 5.1 阶段状态机

```
extract → outline → [outline_refine] → chunk → enrich
                         ↑
                    多轮 refine
                    accept 落盘
```

### 5.2 阶段前置条件与产物

| 阶段 | 前置 | 主要产物 | LLM |
|------|------|----------|-----|
| extract | 源文件 | content.md, images/, manifest | 否 |
| outline | content.md | outline.json | 否 |
| outline_refine | outline.json | refined/mapping/summary（accept 后） | 是 |
| chunk | content + outline(或 refined) | chunks/, index.json | 否 |
| enrich | chunks | 块 metadata 字段 | 可选 |

### 5.3 工作区布局

```text
workspace/
├── content.md
├── images/
├── outline.json
├── outline_refined.json      # accept 后
├── outline_mapping.json
├── outline_refine_summary.md
├── chunks/
│   ├── index.json
│   └── chunk-NNNN.json
├── manifest.json
└── logs/
```

---

## 6. 目录树 LLM 优化（详细需求）

### 6.1 已确认决策

| 项 | 决策 |
|---|---|
| LLM 输入 | 自然语言 + 原始树 + 当前 refined 树 |
| 允许操作 | merge / split / reparent / rename |
| 映射约束 | 每节点必须有 source_refs 或 anchor |
| 交互 | 多轮「指令→预览」，accept 后分块 |
| 历史 | 仅最终树 + 变更摘要 |
| 分块依据 | refined 树 + outline_mapping.json |
| 实现 | LLM 输出 JSON + Validator（重试≤2） |

### 6.2 组件需求

**OutlineRefineSession**（内存）

- `original_outline`（只读）、`current_refined`、`instruction_history`、`round_summaries`
- `status`: active | accepted | discarded
- accept 前不落盘 refined 文件

**OutlineRefineEngine**

- 每轮输出：`outline_refined`、`node_mappings`、`change_summary`
- 输入含 Markdown 标题摘要

**OutlineMappingValidator**

- 校验：映射完整、层级 1–8、范围合法、source_refs 存在
- 默认 **strict=True**（范围不连续阻止 accept）；`--lenient` 仅警告

**RefinedChunkPlanner**

- 按 mapping.markdown_range 或 source_refs 定位内容
- 合并节点 = 连续范围并集
- 超长按 20k token 段落续切

### 6.3 映射规则

| 操作 | source_refs | anchor |
|------|-------------|--------|
| keep | `["n003"]` | 继承 |
| merge | `["n003","n004"]` | block 并集 |
| split | 子集 | 子范围并集=原范围 |
| reparent/rename | 同原节点 | 不变 |

### 6.4 预览输出（不落完整 JSON）

- 节点数 N→M、层级分布变化
- change_summary、校验警告、title diff 列表

### 6.5 错误处理

| 场景 | 行为 |
|------|------|
| JSON 解析失败 | 重试≤2 |
| 校验失败 | 重试≤2，仍失败保留上轮树 |
| LLM 不可用 | 明确错误，不静默回退 |
| accept 后再 refine | 需 reset |
| 未 accept 就 chunk | 使用 outline.json |

---

## 7. 接口需求

### 7.1 CLI 子命令

| 命令 | 说明 |
|------|------|
| `doc-chunk extract` | 提取到工作区 |
| `doc-chunk outline` | 生成目录树 |
| `doc-chunk refine` | 单轮 LLM 优化（预览） |
| `doc-chunk refine-accept` | 落盘优化结果 |
| `doc-chunk refine-discard` | 放弃 session |
| `doc-chunk refine-reset` | 清除已 accept 产物 |
| `doc-chunk chunk` | 分块 |
| `doc-chunk enrich` | 元数据增强 |
| `doc-chunk pipeline` | 端到端 |

详细参数见 [`contracts/cli.md`](../../../specs/001-document-extract-chunk/contracts/cli.md)。

### 7.2 Python API（`doc_chunk.api`）

| 函数 | 说明 |
|------|------|
| `extract_file` / `extract_batch` | 提取 |
| `extract_outline` | 目录树 |
| `refine_outline` / `accept_refined_outline` / `discard` / `reset` | 优化 |
| `chunk_document` | 分块 |
| `enrich_chunks` | 增强 |
| `run_pipeline` | 流水线 |

详细签名见 [`contracts/python-api.md`](../../../specs/001-document-extract-chunk/contracts/python-api.md)。

### 7.3 环境变量

| 变量 | 用途 |
|------|------|
| `OPENAI_API_KEY` | LLM 密钥 |
| `OPENAI_API_BASE` | API 基址 |
| `DOC_CHUNK_LLM_MODEL` | 模型名，默认 gpt-4o-mini |

---

## 8. 数据需求

### 8.1 核心实体

SourceDocument、Extraction Workspace、OutlineNode、RefinedOutline、OutlineMapping、RefineSession（内存）、ContentChunk、ChunkMetadata、Manifest。

详见 [`data-model.md`](../../../specs/001-document-extract-chunk/data-model.md)。

### 8.2 JSON Schema 摘要

所有工作区 JSON 顶层 `schema_version: "1.0"`。

| 文件 | 关键字段 |
|------|----------|
| manifest.json | source, stages, outputs, warnings, errors |
| outline.json | strategy, nodes[].anchor |
| outline_refined.json | derived_from, accepted_at, nodes[].source_refs |
| outline_mapping.json | mappings[].markdown_range, operation |
| chunks/index.json | outline_source, chunks[] |
| chunk-NNNN.json | section_path, metadata |

完整样例见 [`contracts/workspace-schemas.md`](../../../specs/001-document-extract-chunk/contracts/workspace-schemas.md)。

### 8.3 内置分类枚举

- **knowledge_type**: `scheme` | `product` | `qualification` | `other` | custom
- **classification_source**: `rule` | `llm` | `hybrid`

---

## 9. 验收标准

| ID | 标准 |
|----|------|
| SC-001 | Word 提取成功率 ≥95%，图片路径 100% 可解析 |
| SC-002 | 含 TOC/书签文档目录吻合率 ≥90% |
| SC-003 | 标书类分块章节对齐率 ≥95%，任意硬切 <5% |
| SC-004 | LLM 描述准确率 ≥90%（人工抽样） |
| SC-005 | 50 页端到端（无 LLM）< 3 分钟 |
| SC-006 | pip install 后 CLI + import 均可独立/串联调用 |
| SC-007 | skills 通过库 API 集成，无需改块结构 |
| SC-008 | refined 树分块对齐率 ≥95%，合并后无遗漏（前言除外） |

### 9.1 需求追溯矩阵

| FR | User Story | SC |
|----|------------|-----|
| FR-001~004 | US1 | SC-001, SC-005, SC-006 |
| FR-005~006 | US2 | SC-002 |
| FR-007~010 | US3 | SC-003, SC-004, SC-007 |
| FR-015~019 | US4 | SC-008 |
| FR-014 | US1 | SC-006 |
| NFR-001 | — | SC-005 |

---

## 10. 依赖、假设与技术决策

### 10.1 假设

- 用户为开发者/skills agent，非终端业务用户
- 提取阶段不调 LLM；图像语义由下游 skills 负责
- 输出目录默认不覆盖，需显式声明
- 「切片精准」= 目录边界为主 + 20k token 续切为辅 + 8 级章节

### 10.2 外部依赖

- 大模型服务（refine、enrich 可选）
- 行为概念对齐 tender_doctor、tender_knowledge（算法移植，非包依赖）

### 10.3 技术栈（摘要）

| 项 | 选择 |
|----|------|
| 语言 | Python 3.11+ |
| Word | python-docx + lxml |
| PDF | pymupdf |
| 模型 | pydantic v2 |
| CLI | typer |
| 测试 | pytest + jsonschema |
| LLM | OpenAI-compatible 协议 |

完整调研见 [`research.md`](../../../specs/001-document-extract-chunk/research.md)。

### 10.4 参考移植映射

| 能力 | 参考源 |
|------|--------|
| PDF/DOCX 提取 | tender_doctor/extraction/extractors.py |
| 工作区 | tender_doctor/extraction/workspace.py |
| 分块 | tender_doctor/extraction/chunking.py |
| DOCX TOC | tender_knowledge/docx_toc_extractor.py 等 |
| 分类 | tender_knowledge/chunk_classification_service.py |

**后续集成**：替代 tender_knowledge 目录提取与切片所需的 v1.1 改造见
[`2026-06-15-doc-chunk-tender-knowledge-integration.md`](./2026-06-15-doc-chunk-tender-knowledge-integration.md)。

---

## 附录 A：边界与异常

- 不支持格式/加密/损坏文件 → 退出码 4，不写不完整输出
- 混合标题编号 → 低置信标记，不强行合并层级
- 跨章节表格/图片 → 块内保留完整 Markdown 引用
- 重复标题 → section_path 祖先链区分
- LLM 失败 → 降级 + 警告
- refine 映射重叠 → strict 阻止 accept / lenient 警告
- 超大文档 → 进度可观测

## 附录 B：澄清记录索引

完整 Q&A 见 [`specs/001-document-extract-chunk/spec.md`](../../../specs/001-document-extract-chunk/spec.md) Clarifications 节。

---

**文档结束**
