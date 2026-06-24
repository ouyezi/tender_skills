---
name: tender-interpret
description: >-
  Interpret tender documents: extract disqualification items, scoring criteria,
  bid-side risks, and directory requirements. Use when the user asks to interpret
  a bid/tender file, find 废标项, 得分项, 评分标准, 投标风险, or 目录要求.
---

# tender-interpret

从 `doc_chunk` 工作区（或原始文件）提取招标解读结构化 JSON：`interpretation.json`。

## 何时触发

- 「解读招标」「分析标书」「废标项」「得分项」「评分标准」
- 「投标风险」「目录要求」「投标文件组成」
- 用户需要 `interpretation.json` 或四类结构化字段

## 前置条件

```bash
cd tender_skills
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**需要 LLM API Key**（解读阶段调用大模型，默认千问）：

```bash
export LLM_PROVIDER=qwen
export LLM_API_KEY=sk-...
export LLM_BASE_URL=                    # 留空则用 DashScope 兼容端点
export LLM_MODEL=qwen3.6-plus
```

可与 `tender_knowledge/.env` 共用；或 `set -a && source /path/to/tender_knowledge/.env && set +a`。

> **`--no-llm` / FakeLLM 说明**：`tender-insights` CLI 无 `--no-llm` 开关。测试与 CI 请通过 Python API 注入 `FakeLLMClient`（见 `doc_chunk.llm.client`），**不要在生产流程中跳过 LLM**。

## 命令示例

### 已有工作区

```bash
.venv/bin/tender-insights interpret ./output/my-bid
```

### 原始文件（自动 doc-chunk pipeline）

```bash
.venv/bin/tender-insights interpret /path/to/bid.docx \
  -o ./output/my-bid \
  --overwrite
```

### 一次性跑全部语义分析

```bash
.venv/bin/tender-insights all /path/to/bid.docx -o ./output/my-bid --overwrite
```

## 输出路径

| 路径 | 说明 |
|------|------|
| `{workspace}/interpretation.json` | 解读主产物（schema 1.1） |
| `{workspace}/interpret/source_content.md` | OCR  enrichment 后正文（不修改 content.md） |
| `{workspace}/interpret/ocr_cache.json` | 图片 OCR hash 缓存 |
| `{workspace}/manifest.json` | 更新 `stages.interpret` 与 `outputs.interpretation` |

**OCR（默认开启）**：对 `content.md` 引用的图片调用 `qwen-vl-ocr`；可通过 `OCR_ENABLED=false` 关闭。

```bash
export OCR_MODEL=qwen-vl-ocr
export SEGMENT_MIN_TOKENS=2000
export SEGMENT_MAX_TOKENS=12000
```

## 字段说明（`interpretation.json`）

顶层：

| 字段 | 说明 |
|------|------|
| `schema_version` | `"1.1"` |
| `source_workspace` | 工作区绝对路径 |
| `analyzed_at` | ISO8601 分析时间 |
| `segment_count` | 全文分段数 |
| `ocr_image_count` | OCR API 调用次数 |
| `overview` | 概要描述（见下） |
| `directory_outline` | 目录树（供下游目录生成） |

### `overview` — 概要描述

| 字段 | 说明 |
|------|------|
| `summary` | 整份标书解读概要 |
| `disqualification_summary` | 废标项总体说明 |
| `scoring_summary` | 评分办法总体说明 |
| `bid_risk_summary` | 投标风险总体说明 |
| `directory_summary` | 目录/文件组成总体说明 |

### `disqualification_items[]` — 废标项

| 字段 | 说明 |
|------|------|
| `id` | 稳定 ID，如 `dq-001` |
| `title` / `summary` | 标题与摘要 |
| `trigger_condition` | 触发废标的条件 |
| `source_excerpt` | 原文摘录 |
| `section_path` | 章节路径数组 |
| `char_start` / `char_end` | source_content.md 字符锚点（可为 null） |
| `confidence` | 0–1 置信度 |

### `scoring_items[]` — 得分项

| 字段 | 说明 |
|------|------|
| `max_score` | 分值（float，可 null） |
| `weight` | 权重描述，如 `"30%"` |
| `criteria` | 评分标准摘要 |

### `bid_risk_items[]` — 投标视角风险

| 字段 | 说明 |
|------|------|
| `severity` | `high` / `medium` / `low` |
| `risk_category` | 如 `资质`、`商务`、`技术` |

> **与法务区分**：`bid_risk_items` 是**投标执行视角**（资格、符合性、实质性响应等），写入 `interpretation.json`。合规/合同条款风险见 `tender-legal-review` 的 `legal_review.json` → `risk_items`。

### `directory_requirements[]` — 目录/文件组成要求

| 字段 | 说明 |
|------|------|
| `required_sections` | 要求的章节/材料清单 |
| `structure` | 可选树形结构（order/number/title/mandatory） |
| `mandatory` | 是否强制 |

### `directory_outline` — 推荐目录树

| 字段 | 说明 |
|------|------|
| `confidence` | 0–1 |
| `nodes[]` | `id`, `title`, `level`, `order`, `mandatory`, `number` |

## Python API

```python
from pathlib import Path
from tender_insights.api import resolve_workspace_path, interpret_document

ws = resolve_workspace_path(Path("./output/my-bid"))
result = interpret_document(ws)
# result.disqualification_items, result.scoring_items, ...
```

原始文件：

```python
ws = resolve_workspace_path(Path("/path/to/bid.docx"), output_dir=Path("./output/my-bid"), overwrite=True)
interpret_document(ws)
```

## 相关 skills

- `tender-extract` — 若尚无工作区，先提取
- `tender-template` — 模版提取（独立产物）
- `tender-legal-review` — 法务审核（独立 pipeline，不读 interpretation.json）
