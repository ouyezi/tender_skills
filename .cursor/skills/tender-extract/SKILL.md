---
name: tender-extract
description: >-
  Extract tender/bid documents (.docx/.pdf) into a structured doc_chunk workspace
  via doc-chunk pipeline. Use when the user asks to extract, parse, or convert
  a tender document to Markdown, create a workspace, or run doc-chunk on a bid file.
---

# tender-extract

将招标/投标文件（`.docx` / `.pdf`）提取为 `doc_chunk` 标准工作区，供下游解读、模版、法务 skills 消费。

## 何时触发

- 用户要「提取标书」「转 Markdown」「生成工作区」「跑 doc-chunk」
- 下游 skill（interpret / template / legal）需要先准备输入工作区
- 用户上传原始 `.docx` / `.pdf`，尚未有 `manifest.json` + `content.md`

## 前置条件

```bash
cd tender_skills
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

**本 skill 不需要 LLM API Key。** 提取、目录树、文档树、分块均可在无 Key 时运行。

可选环境变量（仅当流水线含 enrich LLM 描述时）：

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_API_BASE=https://api.openai.com/v1   # 可选
export DOC_CHUNK_LLM_MODEL=gpt-4o-mini              # 可选
```

> **`--no-llm` 说明**：`doc-chunk enrich --no-llm` 仅用于测试或离线规则分类，跳过 LLM 块描述。本 skill 默认 `pipeline` 不调 LLM refine；enrich 可用 `--skip-enrich` 完全跳过。

## 命令示例

### 原始文件 → 新工作区

```bash
.venv/bin/doc-chunk pipeline /path/to/bid.docx \
  -o ./output/my-bid \
  --overwrite
```

最短路径（跳过元数据增强）：

```bash
.venv/bin/doc-chunk pipeline /path/to/bid.docx \
  -o ./output/my-bid \
  --overwrite \
  --skip-enrich
```

### 已有工作区（增量步骤）

若工作区已存在，可单独补跑阶段：

```bash
.venv/bin/doc-chunk outline ./output/my-bid
.venv/bin/doc-chunk tree ./output/my-bid
.venv/bin/doc-chunk chunk ./output/my-bid
```

## 输出路径与结构

工作区根目录（`-o` 指定）：

```text
workspace/
├── content.md              # Markdown 正文
├── content.blocks.json     # 块级 char 锚点
├── outline.json            # 目录树（含 char 锚点）
├── document_tree.json      # 块级文档树
├── chunks/                 # 分块 JSON
├── manifest.json           # 阶段状态与产物路径
└── images/                 # 导出图片
```

### 关键字段

| 文件 | 字段 | 说明 |
|------|------|------|
| `manifest.json` | `stages` | 各阶段 success/partial/failed |
| `manifest.json` | `outputs` | 产物文件名映射 |
| `outline.json` | `nodes[].anchor` | `char_start` / `char_end` 章节锚点 |
| `chunks/index.json` | `chunks[]` | 块索引与 outline 关联 |

## Python API

```python
from pathlib import Path
from doc_chunk.api import run_pipeline

run_pipeline(
    Path("/path/to/bid.docx"),
    Path("./output/my-bid"),
    overwrite=True,
    skip_refine=True,
    skip_enrich=True,
)
```

## 相关 skills

- `tender-interpret` — 解读废标/得分/投标风险/目录要求
- `tender-template` — 提取承诺书、授权书等模版
- `tender-legal-review` — 法务合规审核
