---
name: tender-legal-review
description: >-
  Legal/compliance review of tender documents: contract risks and pending
  confirmations. Use when the user asks for 法务审核, 合规风险, 合同条款风险,
  待确认事项, or legal review of a bid file. Distinct from bid-side bid_risk_items
  in interpretation.json.
---

# tender-legal-review

独立法务视角分析招标/合同条款，产出 `legal_review.json`。**不读取** `interpretation.json`，与解读模块完全并行。

## 何时触发

- 「法务审核」「合规风险」「合同条款分析」
- 「违约责任」「付款条款」「知识产权」「争议解决」
- 「待确认事项」「需要向甲方确认的内容」

## 与 interpret 的风险区分（重要）

| 来源 | 字段 | 视角 | 典型内容 |
|------|------|------|----------|
| `tender-interpret` | `interpretation.json` → **`bid_risk_items`** | **投标执行** | 资质符合性、实质性响应、商务/技术投标准备风险 |
| `tender-legal-review` | `legal_review.json` → **`risk_items`** | **法务合规** | 合同不对等、违约/付款/知识产权/争议解决等条款风险 |

两套分析**独立运行**，互不依赖。向用户呈现时务必标明来源，勿将 `bid_risk_items` 与 `risk_items` 混为一谈。

## 前置条件

```bash
cd tender_skills
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**需要 LLM API Key**（默认千问）：

```bash
export LLM_PROVIDER=qwen
export LLM_API_KEY=sk-...
export LLM_BASE_URL=
export LLM_MODEL=qwen3.6-plus
```

> **`--no-llm` 说明**：CLI 无 `--no-llm`。测试请用 Python API + `FakeLLMClient`。**生产法务审核必须走 LLM**。

## 命令示例

### 已有工作区

```bash
.venv/bin/tender-insights legal ./output/my-bid
```

### 原始文件

```bash
.venv/bin/tender-insights legal /path/to/bid.docx \
  -o ./output/my-bid \
  --overwrite
```

### 全部语义分析（interpret + template + legal）

```bash
.venv/bin/tender-insights all /path/to/bid.docx -o ./output/my-bid --overwrite
```

## 输出路径

| 路径 | 说明 |
|------|------|
| `{workspace}/legal_review.json` | 法务审核主产物 |
| `{workspace}/manifest.json` | 更新 `stages.legal` 与 `outputs.legal_review` |

## 字段说明（`legal_review.json`）

顶层：

| 字段 | 说明 |
|------|------|
| `schema_version` | 固定 `"1.0"` |
| `source_workspace` | 工作区路径 |
| `analyzed_at` | ISO8601 |

### `risk_items[]` — 法务合规风险（≠ `bid_risk_items`）

| 字段 | 说明 |
|------|------|
| `id` | 如 `lr-001` |
| `description` | 风险描述 |
| `clause_excerpt` | 涉及条款原文 |
| `risk_type` | 违约/知识产权/付款/争议解决等 |
| `severity` | `high` / `medium` / `low` |
| `section_path` | 章节路径 |
| `char_start` / `char_end` | content.md 锚点 |
| `confidence` | 0–1 |

### `pending_confirmations[]` — 待确认事项

| 字段 | 说明 |
|------|------|
| `id` | 如 `pc-001` |
| `description` | 待确认问题描述 |
| `confirm_with` | 确认方（甲方/法务/业务） |
| `suggested_question` | 建议向对方确认的措辞 |
| `section_path` | 章节路径 |
| `char_start` / `char_end` | 锚点 |
| `confidence` | 0–1 |

## Python API

```python
from pathlib import Path
from tender_insights.api import resolve_workspace_path, review_legal

ws = resolve_workspace_path(Path("./output/my-bid"))
review = review_legal(ws)
# review.risk_items, review.pending_confirmations
```

## 相关 skills

- `tender-extract` — 前置提取
- `tender-interpret` — 投标视角解读（含 `bid_risk_items`，非本 skill 产出）
- `tender-template` — 模版提取
