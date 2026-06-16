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

**需要 LLM API Key**（解读阶段调用大模型）：

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_API_BASE=https://api.openai.com/v1   # 可选，兼容 OpenAI 的网关
export DOC_CHUNK_LLM_MODEL=gpt-4o-mini              # 可选，默认 gpt-4o-mini
```

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
| `{workspace}/interpretation.json` | 解读主产物 |
| `{workspace}/manifest.json` | 更新 `stages.interpret` 与 `outputs.interpretation` |

## 字段说明（`interpretation.json`）

顶层：

| 字段 | 说明 |
|------|------|
| `schema_version` | 固定 `"1.0"` |
| `source_workspace` | 工作区绝对路径 |
| `analyzed_at` | ISO8601 分析时间 |

### `disqualification_items[]` — 废标项

| 字段 | 说明 |
|------|------|
| `id` | 稳定 ID，如 `dq-001` |
| `title` / `summary` | 标题与摘要 |
| `trigger_condition` | 触发废标的条件 |
| `source_excerpt` | 原文摘录 |
| `section_path` | 章节路径数组 |
| `char_start` / `char_end` | content.md 字符锚点（可为 null） |
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
| `mandatory` | 是否强制 |

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
