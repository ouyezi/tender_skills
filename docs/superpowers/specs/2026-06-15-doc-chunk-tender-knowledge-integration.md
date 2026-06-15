# 需求规格：doc_chunk 对接 tender_knowledge（目录提取与章节切片替代）

**版本**: 1.0  
**日期**: 2026-06-15  
**状态**: 草案  
**Feature ID**: `002-doc-chunk-tender-knowledge-integration`  
**前置特性**: [`2026-06-15-doc-chunk-requirements.md`](./2026-06-15-doc-chunk-requirements.md)（v1 基线）  
**消费方**: `tender_knowledge` 实标解析流水线（`actual_bid_parse_runner`）及下游确认向导

---

## 1. 概述

### 1.1 背景

`tender_knowledge` 当前通过自研模块完成标书文档的**目录提取**与**章节切片**：

| 阶段 | 现有模块 | 产出 |
|------|----------|------|
| 全文遍历 | `walk_document` → `docx_hierarchy_inferrer` | `DocumentTreeNode`（heading/paragraph/table/image） |
| 投标目录 | `extract_toc_entries` → `outline_heading_filter` | `BidOutline` / `BidOutlineNode` |
| 候选知识 | `candidate_generate_service` + `build_section_content` | `CandidateKnowledge`（`blocks_v1` 正文） |

`doc_chunk` v1 已具备 extract → outline → chunk 流水线，并在大型餐补标书上验证（616 图、173 目录节点、174 chunk）。  
本需求定义：**在不要求移植 tender_knowledge 领域规则**（内嵌附件检测、伪标题过滤、`structural_only` 等）的前提下，`doc_chunk` 需补齐哪些能力，使 `tender_knowledge` 可将目录提取与切片逻辑**替换为 doc_chunk 工作区输出 + 薄适配层**。

### 1.2 产品目标

| # | 目标 |
|---|------|
| G1 | outline 与 chunk **强一致**：无 Word Heading 样式的编号标书也能按目录节点正确分块 |
| G2 | 产出等价于 `DocumentTreeNode` 的**块级文档树** JSON，供全文树落库 |
| G3 | chunk 携带 **`blocks_v1` 等价结构**，供候选知识正文直接消费 |
| G4 | 提供 **outline ↔ document_tree ↔ chunk ↔ image** 稳定 ID 映射 |
| G5 | Python API 支持**长任务进度回调**，便于接入异步解析任务 |
| G6 | 保持 **不写 tender_knowledge 数据库**；落库由消费方适配层完成 |

### 1.3 范围边界

**In Scope**

- `doc_chunk` 包内：extract / outline / chunk / enrich 的行为与 schema 扩展
- 工作区新增/扩展 JSON 产物与 `manifest.json` 阶段登记
- CLI 与 `doc_chunk.api` 新参数、新命令（如有）
- 契约测试与回归样例（含无 Heading 样式 docx）

**Out of Scope（本特性明确不做）**

- PostgreSQL 写入、`Document` / `BidOutline` / `CandidateKnowledge` 实体落库
- 移植 `embedded_document_detector`、`outline_heading_filter`、`outline_quality_service`
- 模板解析路径：`extract_fixed_paragraph_materials`、变量检测
- Web UI、上传流程、图片 OCR / 视觉 LLM
- 强制默认启用 LLM `refine`（消费方可 `--skip-refine`）

### 1.4 术语对照

| doc_chunk | tender_knowledge | 说明 |
|-----------|------------------|------|
| `outline.json` 节点 | `BidOutlineNode` + `TocEntry` | 投标确认向导中的目录树 |
| `document_tree.json` 节点 | `DocumentTreeNode` | 全文扁平节点流 |
| `chunk`（heading 级） | `CandidateKnowledge` | 一章一条候选（续切块合并或标记） |
| `chunk.blocks[]` | `content` 字段 `blocks_v1` | 富文本与图片渲染 |
| `images/manifest.json` | `document_media_assets` | 适配层注册 UUID |
| `outline.node_id` | `source_node_id` 映射键 | 三联映射中间键 |

### 1.5 现状问题摘要（必须解决）

#### P0-缺陷：outline 与 chunk 数据源不一致

v1 行为：

1. **extract**：仅 Word `Heading N` 样式段落写入 Markdown `#`；其余编号标题保持纯文本。
2. **outline**：可对纯文本行做 `content_heuristic`（中文「第 X 章」、数字编号等），得到完整目录树。
3. **chunk**：`plan_chunks_from_outline` 通过 `_HEADING_RE` 在 `content.md` 中查找 `#` 标题切分；若无匹配则**整篇合并为一块**。

后果：大量标书（无 Heading 样式、靠编号分章）出现 **outline 节点数 ≫ chunk 数**，无法替代 `build_section_content`。

#### P0-缺陷：缺少块级文档树产物

`tender_knowledge` 的 `walk_document` 产出 heading/paragraph/table/image 扁平序列并落库 `DocumentTreeNode`。  
v1 仅有 `content.md` + `chunks/`，消费方若自行反解析 Markdown 将重复实现且易与 chunk 漂移。

#### P0-缺陷：chunk 仅有 Markdown，无 blocks_v1

候选知识、前端富文本渲染依赖 `{"format":"blocks_v1","blocks":[...]}`。v1 chunk JSON 只有 `markdown` 字符串。

---

## 2. 用户场景

### US1 — 无样式编号标书正确分块 (P0)

**作为** tender_knowledge 集成开发者，**我希望**对无 Word Heading 样式、仅靠「1.」「第一章」分章的 docx，chunk 数量与 outline 叶子/章节语义一致，**以便**替换 `generate_for_document`。

| ID | Given | When | Then |
|----|-------|------|------|
| US1-1 | docx 无 Heading 样式，outline 策略为 `content_heuristic`，≥10 个节点 | `pipeline --skip-refine` | `len(chunks)` 与 outline 可切片节点数同量级；不得整篇仅 1 个 chunk（Preface 除外） |
| US1-2 | 同上 | chunk | 每个 chunk 的 `original_node_ids` 非空（除 Preface） |
| US1-3 | docx 含 Heading 样式 | chunk | 行为与 v1 兼容，回归不退化 |
| US1-4 | 某章节正文 > `max_tokens` | chunk | 产生续切块；同一 `original_node_ids`，仅首块 `heading_level` 非 null |

### US2 — 块级文档树导出 (P0)

**作为**集成开发者，**我希望**工作区包含 `document_tree.json`，**以便**适配层一次性写入 `DocumentTreeNode` 而无需重跑 walk 逻辑。

| ID | Given | When | Then |
|----|-------|------|------|
| US2-1 | 含段落、表格、图片的 docx | `pipeline` 或 `extract` + 新阶段 `tree` | 产出 `document_tree.json`，节点含 `node_type` enum |
| US2-2 | outline 已生成 | `document_tree.json` | 每个 heading 节点含 `outline_node_id`（可空） |
| US2-3 | 图片段落 | tree | `node_type=image`，含 `image_ref` 指向 `images/` 相对路径 |

### US3 — blocks_v1 结构化正文 (P0)

**作为**集成开发者，**我希望**每个 chunk JSON 含 `blocks` 数组，**以便**直接序列化为 `CandidateKnowledge.content`。

| ID | Given | When | Then |
|----|-------|------|------|
| US3-1 | chunk 含段落与表格 | chunk | `blocks` 含 `paragraph` / `table`，`text` 字段非空 |
| US3-2 | chunk 含图片 | chunk | `blocks` 含 `image`，`image_ref` 与 `image_refs` 一致 |
| US3-3 | 超长段落 | chunk | 单 block `text` ≤ 32_000 字符（与 tk `MAX_BLOCK_TEXT_CHARS` 对齐） |

### US4 — 稳定 ID 映射 (P0)

**作为**集成开发者，**我希望**有显式映射文件，**以便**设置 `BidOutlineNode.source_node_id` 与 `CandidateKnowledge.source_node_id`。

| ID | Given | When | Then |
|----|-------|------|------|
| US4-1 | outline + tree + chunks 均成功 | 产出 `linkage.json`（或写入 manifest） | 每条 outline 节点可解析到 ≥1 个 tree heading `node_id` 与 ≥1 个 `chunk_id` |
| US4-2 | 续切块 | linkage | 多个 chunk_id 映射同一 `outline_node_id` |

### US5 — 图片清单 (P0)

| ID | Given | When | Then |
|----|-------|------|------|
| US5-1 | docx 含嵌入图 | extract | `images/manifest.json` 列出全部图片：`image_ref`、`content_type`、`source_block_index`（可选 `byte_size`） |
| US5-2 | chunk.blocks image | manifest | `image_ref` 可反查 manifest 条目 |

### US6 — 长任务进度 (P1)

| ID | Given | When | Then |
|----|-------|------|------|
| US6-1 | 大文件 pipeline | `run_pipeline(..., on_progress=cb)` | cb 收到 `stage`（extract/outline/tree/chunk/enrich）与可显示消息 |
| US6-2 | chunk 阶段 | on_progress | 报告已处理 chunk 数 / 预估总数（若可算） |

### US7 — docm 输入 (P1)

| ID | Given | When | Then |
|----|-------|------|------|
| US7-1 | `.docm` 文件 | extract | 成功产出工作区，或明确错误码 + 文档说明需先转 docx |
| US7-2 | 若内置转换 | extract docm | 转换产物写入工作区 `logs/`，manifest 记录 `converted_from` |

### US8 — 外置分类配置 (P1)

| ID | Given | When | Then |
|----|-------|------|------|
| US8-1 | 传入 `--classification-config`（含 product/taxonomy 别名） | enrich | chunk.metadata 含 `product_category_hints`、`chapter_taxonomy_hints`（字符串数组） |
| US8-2 | 无 LLM | enrich --no-llm | 仍输出规则分类 + hints |

---

## 3. 功能需求

### R1 — 基于 outline anchor 的统一分块（P0）

**需求**：`chunk` 阶段 MUST 以 **outline 节点锚点** 为切片主依据，MUST NOT 仅依赖 `content.md` 中的 Markdown `#` 标题。

**实现要求**：

1. **outline 阶段**为每个节点填充可靠锚点，优先级：
   - `anchor.char_start` / `anchor.char_end`（相对 `content.md` 字节或字符偏移，统一用一种并文档化）
   - 或 `anchor.block_start` / `anchor.block_end`（相对 `document_tree.json` 的 `block_index`）
2. **chunk 阶段**新增 `plan_chunks_from_anchors()`（或重构 `plan_chunks_from_outline`）：
   - 按 outline 节点顺序取 `[start, end)` 区间正文；
   - 区间外内容归入 `Preface` chunk（行为与 v1 一致）；
   - 超长区间应用现有 `_split_oversized` 续切逻辑。
3. **refined outline** 路径继续支持 `markdown_range`（已有 `refined_planner`），与原始 outline 锚点策略在契约测试中一并覆盖。
4. `content_heuristic` / `toc` 策略下，即使 `content.md` 无 `#`，chunk 数 MUST 与可切片 outline 节点一致（US1）。

**验收**：新增契约测试 `tests/contract/test_chunk_anchor_alignment.py`，使用无 Heading 样式合成 docx fixture。

---

### R2 — extract 阶段块索引与可选标题升格（P0）

**需求**：extract MUST 为每个逻辑块分配稳定 `block_index`，并写入可供 outline/chunk 引用的侧车数据。

**实现要求**：

1. extract 内部维护 `blocks[]` 元数据（可落盘 `content.blocks.json` 或并入 `document_tree` 生成阶段）：
   - `block_index`、`block_type`（paragraph/table/image/heading）、`char_start`、`char_end`、`text_preview`（可选）
2. **可选策略** `extract --promote-headings auto`（默认 `off` 保持 v1 markdown 外观）：
   - 当与 outline 标题匹配时，将对应行升格为 `#`；**分块仍以 R1 锚点为准**，升格仅用于人类可读 markdown。
3. PDF extract 同步填充 `anchor.page`（已有字段），字符锚点若不可得则仅用 block_index。

---

### R3 — document_tree.json（P0）

**需求**：新增工作区产物 `document_tree.json`，schema_version `1.0`（或 `1.1`，见 §5）。

**节点字段**：

```json
{
  "schema_version": "1.0",
  "nodes": [
    {
      "node_id": "t0001",
      "parent_id": null,
      "outline_node_id": "n001",
      "node_type": "heading",
      "title": "技术方案",
      "level": 1,
      "sort_order": 0,
      "source_block_index": 12,
      "text": null,
      "image_ref": null,
      "needs_review": false
    },
    {
      "node_id": "t0002",
      "parent_id": "t0001",
      "outline_node_id": null,
      "node_type": "paragraph",
      "title": null,
      "level": null,
      "sort_order": 1,
      "source_block_index": 13,
      "text": "正文段落...",
      "image_ref": null,
      "needs_review": false
    }
  ]
}
```

**规则**：

- `node_type` enum：`heading` | `paragraph` | `table` | `image` | `other`（与 tk `DocumentTreeNodeType` 对齐）
- heading 节点：`parent_id` 指向上级 heading；正文/表格/图片：`parent_id` 为所属章节 heading 的 `node_id`
- `sort_order`：文档全局顺序，从 0 递增
- 生成时机：新阶段 `doc-chunk tree WORKSPACE` 或在 `chunk` 前自动执行；`pipeline` 默认串联

**CLI**：`doc-chunk tree WORKSPACE`；`manifest.stages.tree` 登记状态。

---

### R4 — chunk.blocks（blocks_v1 等价）（P0）

**需求**：`chunks/chunk-NNNN.json` MUST 增加 `blocks` 字段；`markdown` 字段保留（向后兼容）。

**块类型**：

| type | 字段 | 说明 |
|------|------|------|
| `paragraph` | `text` | 普通段落 |
| `table` | `text` | 管道符或 markdown 表格文本 |
| `image` | `image_ref` | 相对路径，与 `image_refs[]` 一致 |

**规则**：

1. 由 chunk 区间内的 markdown 解析生成，或 extract/tree 阶段直接累积（推荐后者避免二次解析漂移）
2. 嵌套子章节正文：**不包含**在当前 heading chunk 的 blocks 中（与 tk `build_section_content` 边界一致：子 heading 以下内容由子 chunk 承担）
3. 提供工具函数 `doc_chunk.convert.blocks_to_v1_json(blocks) -> str` 供适配层调用

---

### R5 — linkage.json（P0）

**需求**：产出根级 `linkage.json`，汇总跨产物 ID 映射。

```json
{
  "schema_version": "1.0",
  "outline_source": "original",
  "entries": [
    {
      "outline_node_id": "n003",
      "document_tree_node_ids": ["t0010"],
      "chunk_ids": ["chunk-0003", "chunk-0004"],
      "primary_chunk_id": "chunk-0003"
    }
  ]
}
```

- `primary_chunk_id`：无续切时等于唯一 chunk；有续切时指向 `heading_level != null` 的首块
- `pipeline` 在 chunk 成功后写入；`manifest.outputs.linkage` 登记路径

---

### R6 — images/manifest.json（P0）

```json
{
  "schema_version": "1.0",
  "images": [
    {
      "image_ref": "images/docx-img-001.png",
      "file_name": "docx-img-001.png",
      "content_type": "image/png",
      "byte_size": 102400,
      "source_block_index": 42,
      "width": null,
      "height": null
    }
  ]
}
```

extract 阶段写入/更新；chunk `image_refs` MUST 引用 manifest 中存在的 `image_ref`。

---

### R7 — schema 与 manifest 扩展（P0）

**manifest.json` 扩展**：

```json
{
  "outputs": {
    "document_tree": "document_tree.json",
    "linkage": "linkage.json",
    "images_manifest": "images/manifest.json",
    "content_blocks": "content.blocks.json"
  },
  "stages": {
    "tree": { "status": "success", "warnings": [] }
  }
}
```

**chunks/index.json` 扩展**（可选）：`document_tree_node_id`、`primary_outline_node_id` 便于索引。

**兼容性**：

- 旧消费方仅读 `markdown` 不受影响
- 新字段均为 additive；缺失时视为 v1 工作区

---

### R8 — Python API 进度回调（P1）

```python
def run_pipeline(
    input_path: Path,
    workspace: Path,
    *,
    on_progress: Callable[[str, dict], None] | None = None,
    ...
) -> PipelineResult:
    ...
```

**约定**：

- 第一个参数 `stage`：`extract` | `outline` | `tree` | `chunk` | `enrich`
- 第二个参数 payload：`{"message": str, "current": int, "total": int | None, ...}`
- 回调 MUST NOT 抛异常阻断流水线（内部 catch 并写 warnings）

---

### R9 — docm 处理（P1）

**二选一**（实现时在 plan 中敲定）：

| 方案 | 说明 |
|------|------|
| A. 内置转换 | 依赖 `libreoffice` / `soffice` 或等价工具，转 docx 后走现有 extract；manifest 记录 |
| B. 显式拒绝 | `UnsupportedFormatError` 错误码 4，README 要求调用方先转 docx（与 tk `docm_converter` 分工） |

无论哪种，MUST 在 `detect_file_type` 与文档中行为一致。

---

### R10 — enrich 外置分类 hints（P1）

扩展 `ChunkMetadata`：

```json
{
  "knowledge_type": "scheme",
  "chapter_type": "政策方案",
  "product_category_hints": ["餐补平台", "福利商城"],
  "chapter_taxonomy_hints": ["技术方案", "实施方案"],
  "classification_confidence": 0.82,
  "classification_source": "rule",
  "classification_rationale": "..."
}
```

**配置格式**（`classification_config` YAML 扩展示例）：

```yaml
product_categories:
  - aliases: ["餐补", "福利餐"]
    hint: "餐补平台"
chapter_taxonomies:
  - aliases: ["技术方案", "系统设计"]
    hint: "技术方案"
```

**说明**：hints 为字符串，供 tk 适配层映射 UUID；doc_chunk **不**连接 tk 数据库。

---

### R11 — 候选类型元数据（P2）

chunk.metadata 可选增加：

```json
{
  "suggested_candidate_type": "scheme",
  "suggested_knowledge_type": "scheme"
}
```

由 `candidate_rules.yaml`（chapter_taxonomy hint → type）驱动，规则集与 tk `chapter_candidate_rules.yaml` 可对齐拷贝。

---

## 4. 非功能需求

| ID | 类别 | 要求 |
|----|------|------|
| NF1 | 性能 | 621MB 餐补标书样例，启用 tree+anchor chunk，`pipeline --skip-refine --skip-enrich` 耗时 ≤ v1 的 150% |
| NF2 | 稳定性 | 输出 JSON schema 版本化；`doc-chunk` 契约测试覆盖全部新产物 |
| NF3 | 可测试性 | 提供 `tests/fixtures/no_heading_style.docx`（合成）与锚点对齐黄金文件 |
| NF4 | 文档 | README 文档索引增加本规格；`workspace-schemas.md` 同步更新 |
| NF5 | 依赖 | 不新增强制运行时 DB 依赖；可选 docm 转换工具除外 |

---

## 5. Schema 版本策略

| 文件 | 版本 | 说明 |
|------|------|------|
| 既有 manifest / outline / chunk | `1.0` | additive 字段不升版 |
| `document_tree.json` | `1.0` | 新文件 |
| `linkage.json` | `1.0` | 新文件 |
| `images/manifest.json` | `1.0` | 新文件 |

若未来破坏性变更，整体升为 `schema_version: "1.1"` 并在 manifest 声明 `feature_flags`。

---

## 6. CLI 变更摘要

| 命令 | 变更 |
|------|------|
| `doc-chunk tree WORKSPACE` | **新增**：由 content + outline 生成 `document_tree.json` |
| `doc-chunk chunk WORKSPACE` | 默认改用 anchor 分块；`--markdown-headings-only` 保留 v1 行为用于回归 |
| `doc-chunk pipeline` | 默认串联 `tree`；产出 linkage |
| `doc-chunk extract` | 写出 `images/manifest.json`、`content.blocks.json`（可选侧车） |

---

## 7. tender_knowledge 适配层（参考，非本仓库实现）

供联调对齐，**不在 doc_chunk 实现**：

```
doc_chunk pipeline → workspace/
        ↓
tk.adapter.doc_chunk_import
  - document_tree.json → DocumentTreeNode + media assets 注册
  - outline.json + linkage.json → BidOutlineNode（source_node_id）
  - chunks/*.blocks → CandidateKnowledge.content (blocks_v1)
  - chunk.metadata hints → chunk_classification_service 预填
```

---

## 8. 交付切片建议

```text
P0（阻断集成）
  R1  anchor 分块
  R2  块索引侧车
  R3  document_tree.json
  R4  chunk.blocks
  R5  linkage.json
  R6  images/manifest.json
  R7  manifest 扩展 + 契约测试

P1（体验与运维）
  R8  进度回调
  R9  docm 策略
  R10 enrich hints

P2（可选）
  R11 候选类型元数据
```

---

## 9. 验收标准（特性完成定义）

1. 餐补标书样例：`outline` 节点数与「主 chunk」数比例在 `[0.8, 1.2]`（排除 Preface 与续切块）
2. 合成无 Heading docx：US1 全部通过
3. `document_tree.json` 节点类型分布含 paragraph/table/image
4. 任意 chunk 的 `blocks` 经 tk `content_blocks.blocks_v1()` 可序列化且无异常
5. `linkage.json` 每个 outline 节点至少一条 entry（flat_fallback 单节点除外）
6. `pytest tests/contract -v` 全绿；README 文档索引含本规格

---

## 10. 参考

| 文档 | 路径 |
|------|------|
| doc_chunk v1 需求 | [`2026-06-15-doc-chunk-requirements.md`](./2026-06-15-doc-chunk-requirements.md) |
| 工作区 schema | [`specs/001-document-extract-chunk/contracts/workspace-schemas.md`](../../../specs/001-document-extract-chunk/contracts/workspace-schemas.md) |
| tk 章节切片设计 | `tender_knowledge/docs/superpowers/specs/2026-06-14-knowledge-visibility-design.md` §6 |
| tk DocumentTreeNode | `tender_knowledge/backend/src/models/document_tree_node.py` |
| tk blocks_v1 | `tender_knowledge/backend/src/services/content_blocks.py` |

---

## 11. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-06-15 | 初稿：tk 集成所需的 doc_chunk 改造范围 |
