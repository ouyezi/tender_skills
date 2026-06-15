# Data Model: doc_chunk

**Feature**: `001-document-extract-chunk`  
**Date**: 2026-06-15

## Overview

所有持久化实体以 JSON 或 Markdown 文件存储于 **Extraction Workspace**。内存实体（Refine Session）不落盘直至 `accept`。

```
SourceDocument ──extract──▶ Workspace ──outline──▶ OutlineTree
                                    │
                                    ├──refine(session)──▶ RefinedOutline + OutlineMapping
                                    │
                                    └──chunk──▶ ContentChunk[]
                                           └──enrich──▶ ChunkMetadata
```

---

## SourceDocument

输入侧瞬态实体，不单独落盘（信息写入 manifest.source）。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| path | Path | yes | 绝对或相对路径 |
| file_name | str | yes | |
| file_type | enum | yes | `docx` \| `doc` \| `docm` \| `pdf` |
| title | str | no | 可识别时填充 |

**Validation**: 后缀与 `file_type` 一致；不支持格式抛 `UnsupportedFormatError`。

---

## Extraction Workspace

| Path | Entity |
|------|--------|
| `content.md` | Markdown 正文 |
| `images/` | 导出图片 |
| `outline.json` | OutlineTree |
| `outline_refined.json` | RefinedOutline（accept 后） |
| `outline_mapping.json` | OutlineMappingFile |
| `outline_refine_summary.md` | 人类可读摘要 |
| `chunks/` | ContentChunk 文件 |
| `chunks/index.json` | 块索引 |
| `manifest.json` | Manifest |
| `logs/` | 运行日志 |

**Lifecycle**: `create(overwrite=False)` → 各阶段更新 manifest.stages → 完成

---

## OutlineNode (outline.json)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| node_id | str | yes | 如 `n001` |
| title | str | yes | |
| level | int | yes | 1–8 |
| parent_id | str \| null | yes | |
| sort_order | int | yes | 同级排序 |
| strategy | str | no | 树级策略冗余 |
| anchor | Anchor | yes | 见下 |
| needs_review | bool | no | 默认 false |

### Anchor

| Field | Type | Notes |
|-------|------|-------|
| block_index | int | DOCX 块索引 |
| page | int | PDF 页码 |
| char_start | int | Markdown 字符偏移（可选） |
| char_end | int | |

**OutlineTree 文件**:

```json
{
  "schema_version": "1.0",
  "strategy": "toc",
  "nodes": [ "...OutlineNode" ]
}
```

**Validation**:
- `level` ∈ [1, 8]
- `parent_id` 必须指向已存在节点或 null
- 无环
- `sort_order` 在同级唯一

---

## RefinedOutlineNode (outline_refined.json)

继承 OutlineNode 语义，额外字段：

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| source_refs | list[str] | yes* | 原始 node_id 列表 |
| derived_from | str | file | 固定 `outline.json` |

\* 与 `anchor` 至少其一非空（FR-016）

---

## OutlineMappingEntry

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| refined_node_id | str | yes | |
| source_node_ids | list[str] | yes | |
| markdown_range | CharRange | yes | |
| operation | enum | yes | `merge` \| `split` \| `reparent` \| `rename` \| `keep` |

### CharRange

| Field | Type |
|-------|------|
| char_start | int |
| char_end | int |

**Validation (strict mode)**:
- 所有 `source_node_ids` 存在于原始树
- 合并节点的 `markdown_range` 覆盖连续内容
- 各 mapping 范围不重叠（默认仅叶子切块）
- 原始节点集合被覆盖（可配置）

---

## RefineSession (memory only)

| Field | Type | Notes |
|-------|------|-------|
| workspace | Path | |
| original_outline | OutlineTree | 只读 |
| current_refined | OutlineTree \| null | |
| instruction_history | list[str] | |
| round_summaries | list[str] | |
| status | enum | `active` \| `accepted` \| `discarded` |

**Transitions**:
- `active` + refine OK → `active`（更新 current_refined）
- `active` + accept → `accepted`（落盘，session 锁定）
- `active` + discard → `discarded`
- `accepted` + reset → 新 session `active`

---

## ContentChunk

单块文件 `chunks/chunk-NNNN.json` + 索引条目。

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| chunk_id | str | yes | `chunk-0001` |
| title | str | yes | |
| section_path | list[str] | yes | 最深 8 级 |
| heading_level | int \| null | yes | 1–8 或 null |
| markdown | str | yes | 块正文 |
| source_file | str | yes | |
| source_ranges | list[Anchor] | yes | |
| token_estimate | int | yes | |
| image_refs | list[str] | no | |
| previous_chunk_id | str \| null | no | |
| next_chunk_id | str \| null | no | |
| outline_source | enum | yes | `original` \| `refined` |
| refined_node_id | str \| null | refined 时必填 |
| original_node_ids | list[str] | no | |
| status | enum | yes | `success` \| `partial` |

**Validation**:
- 续切块：`heading_level=null`，`section_path` 继承
- 前言块：`section_path=[]`，`heading_level=null`

---

## ChunkMetadata

嵌入 chunk JSON 的 `metadata` 字段或 sidecar（v1 嵌入 chunk）。

| Field | Type | Notes |
|-------|------|-------|
| description | str | LLM 1–3 句 |
| knowledge_type | enum | scheme/product/qualification/other/custom |
| chapter_type | str | 内置或自定义 |
| classification_confidence | float | 0–1 |
| classification_source | enum | rule/llm/hybrid |
| classification_rationale | str | |
| generated_at | datetime | |

---

## Manifest

| Field | Type | Notes |
|-------|------|-------|
| schema_version | str | `1.0` |
| status | enum | success/partial_success/failed |
| source | object | SourceDocument 摘要 |
| stages | object | 各阶段状态与时间戳 |
| outputs | object | 产物路径 |
| warnings | list[str] | |
| errors | list[str] | |
| batch_summary | object | 批量时逐文件结果 |

### stages 键

`extract` | `outline` | `outline_refine` | `chunk` | `enrich`

每阶段：`{ "status", "started_at", "finished_at", "warnings" }`

---

## Relationships

```text
OutlineTree 1──* OutlineNode
RefinedOutline 1──* RefinedOutlineNode
RefinedOutlineNode *──* OutlineNode (via source_refs)
OutlineMappingEntry *──1 RefinedOutlineNode
ContentChunk *──1 OutlineNode | RefinedOutlineNode
ContentChunk 1──1 ChunkMetadata (optional enrich)
Manifest 1──1 Workspace
```

---

## State: Pipeline Stage Dependencies

```text
extract ──▶ outline ──▶ [outline_refine] ──▶ chunk ──▶ enrich
              │              │ optional
              └──────────────┘
chunk 可读 outline.json 或 outline_refined.json（优先后者若存在且 accepted）
```

---

## Index Files

### chunks/index.json

```json
{
  "schema_version": "1.0",
  "chunks": [
    {
      "chunk_id": "chunk-0001",
      "title": "...",
      "section_path": ["..."],
      "heading_level": 2,
      "token_estimate": 1200,
      "path": "chunks/chunk-0001.json"
    }
  ]
}
```
