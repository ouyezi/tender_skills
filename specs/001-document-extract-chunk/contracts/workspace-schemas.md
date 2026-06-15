# Workspace JSON Schemas

**Schema version**: `1.0`  
**Date**: 2026-06-15

所有工作区 JSON 文件 MUST 包含顶层 `schema_version: "1.0"`。

---

## manifest.json

```json
{
  "schema_version": "1.0",
  "status": "success",
  "source": {
    "path": "/path/to/bid.docx",
    "file_name": "bid.docx",
    "file_type": "docx",
    "title": "XX项目投标文件"
  },
  "stages": {
    "extract": {
      "status": "success",
      "started_at": "2026-06-15T10:00:00Z",
      "finished_at": "2026-06-15T10:00:30Z",
      "warnings": []
    },
    "outline": { "status": "success", "warnings": [] },
    "outline_refine": { "status": "skipped", "warnings": [] },
    "chunk": { "status": "success", "warnings": [] },
    "enrich": { "status": "success", "warnings": [] }
  },
  "outputs": {
    "content": "content.md",
    "images_dir": "images",
    "outline": "outline.json",
    "outline_refined": "outline_refined.json",
    "outline_mapping": "outline_mapping.json",
    "chunks_dir": "chunks",
    "chunks_index": "chunks/index.json"
  },
  "warnings": [],
  "errors": []
}
```

**status enum**: `success` | `partial_success` | `failed`

---

## outline.json

```json
{
  "schema_version": "1.0",
  "strategy": "toc",
  "nodes": [
    {
      "node_id": "n001",
      "title": "响应文件格式",
      "level": 1,
      "parent_id": null,
      "sort_order": 0,
      "anchor": { "block_index": 12, "page": null },
      "needs_review": false
    }
  ]
}
```

**strategy enum**: `toc` | `heading_heuristic` | `content_heuristic` | `flat_fallback`

---

## outline_refined.json

```json
{
  "schema_version": "1.0",
  "derived_from": "outline.json",
  "accepted_at": "2026-06-15T10:15:00Z",
  "nodes": [
    {
      "node_id": "r001",
      "title": "资格与商务文件",
      "level": 2,
      "parent_id": "r000",
      "sort_order": 1,
      "source_refs": ["n003", "n004"],
      "anchor": { "block_start": 45, "block_end": 120 },
      "needs_review": false
    }
  ]
}
```

---

## outline_mapping.json

```json
{
  "schema_version": "1.0",
  "mappings": [
    {
      "refined_node_id": "r001",
      "source_node_ids": ["n003", "n004"],
      "markdown_range": { "char_start": 1200, "char_end": 4500 },
      "operation": "merge"
    }
  ]
}
```

**operation enum**: `merge` | `split` | `reparent` | `rename` | `keep`

---

## chunks/index.json

```json
{
  "schema_version": "1.0",
  "outline_source": "refined",
  "chunks": [
    {
      "chunk_id": "chunk-0001",
      "title": "前言",
      "section_path": [],
      "heading_level": null,
      "token_estimate": 320,
      "refined_node_id": null,
      "original_node_ids": [],
      "path": "chunks/chunk-0001.json"
    },
    {
      "chunk_id": "chunk-0002",
      "title": "资格与商务文件",
      "section_path": ["响应文件格式", "资格与商务文件"],
      "heading_level": 2,
      "token_estimate": 8500,
      "refined_node_id": "r001",
      "original_node_ids": ["n003", "n004"],
      "path": "chunks/chunk-0002.json"
    }
  ]
}
```

---

## chunks/chunk-NNNN.json

```json
{
  "schema_version": "1.0",
  "chunk_id": "chunk-0002",
  "title": "资格与商务文件",
  "section_path": ["响应文件格式", "资格与商务文件"],
  "heading_level": 2,
  "markdown": "## 资格与商务文件\n\n...",
  "source_file": "/path/to/bid.docx",
  "source_ranges": [{ "char_start": 1200, "char_end": 4500 }],
  "token_estimate": 8500,
  "image_refs": ["images/docx-img-001.png"],
  "previous_chunk_id": "chunk-0001",
  "next_chunk_id": "chunk-0003",
  "outline_source": "refined",
  "refined_node_id": "r001",
  "original_node_ids": ["n003", "n004"],
  "status": "success",
  "metadata": {
    "description": "本章合并原资格与商务要求，列明投标人需提交的证明材料。",
    "knowledge_type": "qualification",
    "chapter_type": "资质证明",
    "product_category_hints": ["餐补平台"],
    "chapter_taxonomy_hints": ["技术方案"],
    "classification_confidence": 0.85,
    "classification_source": "hybrid",
    "classification_rationale": "标题含资格关键词；LLM 确认",
    "generated_at": "2026-06-15T10:20:00Z"
  },
  "blocks": [
    { "type": "paragraph", "text": "资格与商务文件正文..." },
    { "type": "image", "image_ref": "images/docx-img-001.png" }
  ]
}
```

---

## content.blocks.json

```json
{
  "schema_version": "1.0",
  "blocks": [
    {
      "block_index": 0,
      "block_type": "paragraph",
      "char_start": 0,
      "char_end": 12,
      "text_preview": "1. 技术方案",
      "image_ref": null
    }
  ]
}
```

**block_type enum**: `paragraph` | `table` | `image` | `heading`

---

## document_tree.json

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
      "source_block_index": 0,
      "text": null,
      "image_ref": null,
      "needs_review": false
    }
  ]
}
```

**node_type enum**: `heading` | `paragraph` | `table` | `image` | `other`

---

## linkage.json

每个 `outline.json` 节点 MUST 有一条 entry（`flat_fallback` 单节点文档例外）。无对应 chunk 时 `chunk_ids` 为空数组，`document_tree_node_ids` 仍须非空。

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

---

## images/manifest.json

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

---

## blocks_v1 导出（适配层）

`doc_chunk.convert.blocks_to_v1_json` 将 `chunk.blocks` 转为 tender_knowledge 可消费的 `blocks_v1` JSON：

- 无 `asset_id` 映射：`{"type":"image","image_ref":"images/..."}`
- 有映射（推荐）：`{"type":"image","asset_id":"<uuid>","image_ref":"images/..."}`

工作区 `chunk-*.json` 内 `blocks[]` 仍使用 `image_ref`；`asset_id` 由适配层在落库前通过 `images/manifest.json` 注入 `image_ref_to_asset_id` 映射生成。

---

## Contract Tests

契约测试 MUST 验证：

1. 所有样例 JSON 通过 pydantic 模型解析
2. `model_json_schema()` 导出与本文档字段一致
3. 必填字段缺失时解析失败
4. `level` 超出 1–8 时验证失败
5. `chunk_id` 链接双向一致（previous/next）

测试路径：`tests/contract/test_workspace_schemas.py`

---

## Schema Evolution

| Version | Change |
|---------|--------|
| 1.0 | 初始版本，含 refined outline 字段 |

未来版本 MUST 递增 `schema_version` 并提供读取旧版的兼容层。
