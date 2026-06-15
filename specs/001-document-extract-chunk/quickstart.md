# Quickstart: doc_chunk 验证指南

**Feature**: `001-document-extract-chunk`  
**Date**: 2026-06-15

本指南用于验证流水线端到端行为。实现完成后按下列步骤执行。

## Prerequisites

- Python 3.11+
- 仓库根目录：`tender_skills/`
- 测试文档：一份含多级标题的 `.docx` 或 `.pdf`（可用 `../tender_doctor` 样例）
- LLM 验证（refine/enrich）：配置 `OPENAI_API_KEY`

## Setup

```bash
cd /path/to/tender_skills
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Scenario 1: 提取（User Story 1）

```bash
doc-chunk extract ./samples/bid.docx -o ./output/bid-workspace
```

**Expected**:
- `output/bid-workspace/content.md` 存在且含标题 Markdown
- `output/bid-workspace/images/` 含嵌入图片
- `output/bid-workspace/manifest.json` status=`success`
- 图片引用路径可解析

## Scenario 2: 目录树（User Story 2）

```bash
doc-chunk outline ./output/bid-workspace
```

**Expected**:
- `outline.json` 含 `schema_version`、`strategy`、`nodes`
- 节点 `level` 在 1–8
- 含 `anchor` 位置信息

## Scenario 3: 分块（User Story 3，原始树）

```bash
doc-chunk chunk ./output/bid-workspace --use-original
```

**Expected**:
- `chunks/index.json` 与 `chunks/chunk-*.json` 生成
- 每块含 `section_path`、`heading_level`、链接字段
- 块边界与章节起点对齐（人工抽查 ≥95%）

## Scenario 4: 目录树优化 + 分块（User Story 4）

```bash
export OPENAI_API_KEY=sk-...

doc-chunk refine ./output/bid-workspace \
  -i "合并标题中包含'资格'和'商务'的相邻章节"

# 检查 stdout 预览 JSON validation.passed=true

doc-chunk refine-accept ./output/bid-workspace

doc-chunk chunk ./output/bid-workspace
```

**Expected**:
- `outline_refined.json`、`outline_mapping.json`、`outline_refine_summary.md` 落盘
- `chunks/index.json` 中 `outline_source=refined`
- 合并章节对应单块，`original_node_ids` 含多个原始节点

## Scenario 5: 元数据增强

```bash
doc-chunk enrich ./output/bid-workspace
```

**Expected**:
- 每块 `metadata.description` 非空（LLM 可用时）
- `metadata.knowledge_type` 为内置枚举之一
- LLM 不可用时：`doc-chunk enrich --no-llm` 仍有规则分类

## Scenario 6: 端到端流水线

```bash
doc-chunk pipeline ./samples/bid.docx -o ./output/pipeline-run --skip-refine
```

**Expected**:
- 3 分钟内完成（50 页内，SC-005）
- extract + outline + chunk 阶段均 success

## Scenario 7: Python API（skills 集成）

```python
from pathlib import Path
from doc_chunk.api import extract_file, extract_outline, chunk_document

ws = Path("output/api-test")
extract_file("samples/bid.docx", ws)
extract_outline(ws)
index = chunk_document(ws)
assert len(index.chunks) > 0
```

## Scenario 8: 批量 continue-on-error

```bash
doc-chunk extract ./samples/mixed-dir -o ./output/batch
# mixed-dir 含 1 个损坏文件 + 2 个正常文件
echo $?  # 期望 2（部分成功）
```

## Automated Tests

```bash
pytest tests/unit -q
pytest tests/contract -q
pytest tests/integration -q
# 可选外部样例：
pytest tests/integration -m external_samples
```

## Troubleshooting

| 问题 | 检查 |
|------|------|
| refine 失败 | `OPENAI_API_KEY`、stdout validation.errors |
| chunk 用了原始树 | 是否 `refine-accept`；或加 `--use-original` |
| 图片链接断裂 | `content.md` 中路径是否相对 `images/` |
| 工作区已存在 | 加 `--overwrite` |

## References

- [数据模型](./data-model.md)
- [CLI 契约](./contracts/cli.md)
- [Python API](./contracts/python-api.md)
- [JSON Schema](./contracts/workspace-schemas.md)
- [实现计划](./plan.md)
