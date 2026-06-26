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

模版提取依赖 LLM 分片规划与逐片识别。建议配置（默认千问）：

```bash
export LLM_PROVIDER=qwen
export LLM_API_KEY=sk-...
export LLM_BASE_URL=
export LLM_MODEL=qwen3.7-max
```

模版分片与规划专用配置（见 `.env.example`）：

```bash
export TEMPLATE_WHOLE_DOC_MAX_CHARS=6000    # 低于此值整篇一片
export TEMPLATE_SHARD_MAX_CHARS=6000        # 单片输入上限（超出则拆分）
export TEMPLATE_CHAR_CHUNK_OVERLAP=500      # 字符块切分重叠
export TEMPLATE_PLAN_ENABLED=true           # false 时跳过 LLM plan，仅保留确定性分片
```

> **生产环境勿跳过 LLM**。测试请用 Python API + `TemplateFakeLLM` 注入，勿依赖旧关键词检测器。

## 提取流水线（LLM v1.1）

```
outline.json + content.md
    ↓
[sharder] 确定性分片（outline L1 → 子节点 → heading → char）
    ↓
[planner] 可选 LLM plan → templates/plan.json
    ↓
[extractor] 逐片 LLM 提取 → 每模版 markdown 字段为完整正文
    ↓
写入 templates/*.md（直接使用 LLM 输出，不按坐标截取）
    ↓
[merger] 去重 → templates/index.json (schema v1.1)
```

**旧 `detector.py` 关键词匹配已废弃**，仅保留于单元测试；生产路径统一走上述 LLM pipeline。

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
├── plan.json               # 分片计划（TemplatePlanFile schema）
├── index.json              # 模版索引（TemplatesIndexFile schema v1.1）
├── commitment-001.md       # 承诺书正文
├── authorization-001.md    # 授权书正文
└── ...
```

`manifest.json` 更新 `stages.template` 与 `outputs.templates`。

## 字段说明（`templates/index.json`）

顶层：

| 字段 | 说明 |
|------|------|
| `schema_version` | `"1.1"` |
| `analyzed_at` | ISO8601 |
| `plan_ref` | 固定 `"templates/plan.json"` |
| `shard_count` | 分片总数 |
| `templates[]` | 模版条目列表 |

### `templates/plan.json`

| 字段 | 说明 |
|------|------|
| `shard_count` | 分片数 |
| `shards[]` | 每片 `shard_id`、`strategy`、`section_path`、`char_start`/`char_end` |
| `llm_notes` | LLM plan 补充说明（可选） |
| `priority_sections` | LLM 标注的高优先级章节（可选） |

### `templates[]` 每条

| 字段 | 说明 |
|------|------|
| `id` | 稳定 ID，如 `tpl-001` |
| `type` | `commitment` / `authorization` / `declaration` / `other` |
| `type_label` | 中文标签，如「承诺书」 |
| `title` | 模版标题 |
| `section_path` | 章节路径 |
| `file` | 相对工作区的 Markdown 路径（LLM 输出的完整模版正文） |
| `char_start` / `char_end` | 已弃用，多为 `null` |
| `confidence` | 0–1 |
| `extraction_method` | `llm` |
| `shard_id` | 来源分片 ID（可选） |

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
from tender_insights.api import resolve_workspace_path, run_template_job, extract_templates

ws = resolve_workspace_path(Path("./output/my-bid"))

# 推荐：带进度回调与 llm_calls.jsonl 日志
index = run_template_job(ws, on_progress=lambda stage, payload: print(stage, payload))

# 兼容别名（内部同样走 LLM pipeline）
index = extract_templates(ws)
# index.templates[0].file → "templates/authorization-001.md"
```

进度阶段：`template_plan` → `template_extract` → `template_merge`。

## Viewer

解读页（`interpret.html`）提供独立 **「提取模版」** 按钮（`#template-btn`）：

- 上传新文件：`POST /api/interpret/upload?job_kind=template`
- 已有会话：`POST /api/interpret/sessions/{id}/template`

进度条展示 `template_plan` / `template_extract` / `template_merge` 阶段；完成后自动切换到「模版」Tab。

「开始解读」流程末尾也会自动调用 `run_template_job`（`include_template=True`）。

## 相关 skills

- `tender-extract` — 前置提取
- `tender-interpret` — 解读（独立产物）
- `tender-legal-review` — 法务（独立产物）
