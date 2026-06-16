---
name: tender-template
description: >-
  Extract embedded tender submission templates (commitment letters, authorization
  forms, declarations) from bid documents. Use when the user asks for 承诺书模版,
  授权书, 声明函, 附件格式, or template extraction from a tender file.
---

# tender-template

从招标文件正文中识别并切片嵌入的提交模版（承诺书、授权书、声明函等），写入 `templates/` 目录。

## 何时触发

- 「提取模版」「承诺书格式」「授权书模版」「声明函」
- 「附件格式」「投标文件模版」
- 用户需要 `templates/index.json` 或独立 `.md` 模版文件

## 前置条件

```bash
cd tender_skills
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

模版分类可能调用 LLM（规则优先）。建议配置（默认千问）：

```bash
export LLM_PROVIDER=qwen
export LLM_API_KEY=sk-...
export LLM_BASE_URL=
export LLM_MODEL=qwen3.6-plus
```

> **`--no-llm` 说明**：CLI 无 `--no-llm`。测试请用 Python API + `FakeLLMClient` 注入。**生产环境勿跳过 LLM**（若 classifier 走 LLM 兜底）。

## 命令示例

### 已有工作区

```bash
.venv/bin/tender-insights template ./output/my-bid
```

### 原始文件

```bash
.venv/bin/tender-insights template /path/to/bid.docx \
  -o ./output/my-bid \
  --overwrite
```

## 输出路径

```text
{workspace}/templates/
├── index.json              # 模版索引（TemplatesIndexFile schema）
├── commitment-001.md       # 承诺书正文
├── authorization-001.md    # 授权书正文
└── ...
```

`manifest.json` 更新 `stages.template` 与 `outputs.templates`。

## 字段说明（`templates/index.json`）

顶层：

| 字段 | 说明 |
|------|------|
| `schema_version` | 固定 `"1.0"` |
| `analyzed_at` | ISO8601 |
| `templates[]` | 模版条目列表 |

### `templates[]` 每条

| 字段 | 说明 |
|------|------|
| `id` | 稳定 ID，如 `tpl-001` |
| `type` | `commitment` / `authorization` / `declaration` / `other` |
| `type_label` | 中文标签，如「承诺书」 |
| `title` | 模版标题 |
| `section_path` | 章节路径 |
| `file` | 相对工作区的 Markdown 路径，如 `templates/commitment-001.md` |
| `char_start` / `char_end` | content.md 锚点 |
| `confidence` | 0–1 |

### 模版类型

| `type` | `type_label` | 关键词示例 |
|--------|--------------|------------|
| `commitment` | 承诺书 | 承诺书、诚信承诺 |
| `authorization` | 授权书 | 授权书、授权委托 |
| `declaration` | 声明函 | 声明函、声明书 |
| `other` | 其他 | 兜底 |

## Python API

```python
from pathlib import Path
from tender_insights.api import resolve_workspace_path, extract_templates

ws = resolve_workspace_path(Path("./output/my-bid"))
index = extract_templates(ws)
# index.templates[0].file → "templates/commitment-001.md"
```

## 相关 skills

- `tender-extract` — 前置提取
- `tender-interpret` — 解读（独立产物）
- `tender-legal-review` — 法务（独立产物）
