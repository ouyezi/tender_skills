# doc_chunk

独立 Python 包，将 Word/PDF 标书文档处理为结构化工作区，供 tender_skills 及下游 agent 消费。

**流水线：** 提取 → 目录树 → （可选）LLM 目录优化 → 分块 → 元数据增强

- 支持 `.docx` / `.doc` / `.pdf`（`.docm` 需先转 `.docx`）
- CLI：`doc-chunk` · 库 API：`doc_chunk.api`
- 输出稳定 JSON schema（`schema_version: 1.0`）
- 提取阶段**不做**图片 OCR（图像语义由下游 skills 处理）

完整需求见 [`docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md`](docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md)。  
**tender_knowledge 集成**见 [`docs/superpowers/specs/2026-06-15-doc-chunk-tender-knowledge-integration.md`](docs/superpowers/specs/2026-06-15-doc-chunk-tender-knowledge-integration.md)。

---

## 安装

```bash
cd tender_skills
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

验证：

```bash
doc-chunk --help
python -m pytest tests/ -q
```

---

## 快速开始

### 一键流水线（推荐）

不含 LLM 的最短路径（提取 + 目录树 + 分块）：

```bash
doc-chunk pipeline /path/to/bid.docx \
  -o ./output/my-bid \
  --overwrite \
  --skip-refine \
  --skip-enrich
```

### 分步执行

```bash
# 提取 → content.md + images/ + content.blocks.json
doc-chunk extract /path/to/bid.docx -o ./output/my-bid

# 无 Word Heading 样式时，升格编号行为 Markdown 标题（分块仍走锚点）
doc-chunk extract /path/to/bid.docx -o ./output/my-bid --promote-headings auto

# 2. 目录树 → outline.json
doc-chunk outline ./output/my-bid

# 3. 分块 → chunks/
doc-chunk chunk ./output/my-bid

# 4. 元数据（可选，需 LLM 或使用 --no-llm 仅规则分类）
doc-chunk enrich ./output/my-bid --no-llm
```

### 真实样例

已对 621MB 餐补标书跑通：

```bash
doc-chunk pipeline \
  "/Users/tongqianni/xlab/标书助力/测试招投标文件/标书诊断/中银上海/【2中银保险上海分公司】餐补标书.docx" \
  -o ./output/zhongyin-canbu \
  --overwrite \
  --skip-refine \
  --skip-enrich
```

典型产出：616 张图片、173 个目录节点、174 个 chunk，约 3 秒（不含 LLM）。

---

## 工作区结构

每次处理在 `-o` 指定目录生成：

```text
workspace/
├── content.md              # Markdown 正文
├── content.blocks.json     # 块索引侧车（char 锚点）
├── document_tree.json      # 块级文档树（tk DocumentTreeNode 等价）
├── linkage.json            # outline ↔ tree ↔ chunk ID 映射
├── images/
│   ├── manifest.json       # 图片清单
│   └── docx-img-001.png
├── outline.json            # 原始目录树
├── outline_refined.json    # LLM 优化后（accept 后才有）
├── outline_mapping.json    # 优化节点 → 原文映射
├── outline_refine_summary.md
├── chunks/
│   ├── index.json          # 块索引
│   └── chunk-0001.json     # 单块（含 blocks、markdown 等）
├── manifest.json           # 阶段状态与产物路径
└── logs/
```

---

## CLI 命令参考

| 命令 | 说明 |
|------|------|
| `extract INPUT -o DIR` | 提取单文件；`INPUT` 为目录时批量处理 |
| `outline WORKSPACE` | 从 `content.md` 生成 `outline.json` |
| `tree WORKSPACE` | 生成 `document_tree.json` |
| `refine WORKSPACE -i "指令"` | LLM 优化目录树（预览，不落盘） |
| `refine-accept WORKSPACE` | 确认并写入 `outline_refined.json` 等 |
| `refine-discard WORKSPACE` | 放弃当前 refine session |
| `refine-reset WORKSPACE` | 清除已 accept 的优化结果，重新开始 |
| `chunk WORKSPACE` | 按 outline 锚点分块（默认） |
| `enrich WORKSPACE` | 块描述 + 分类 |
| `pipeline INPUT -o DIR` | 端到端串联（含 tree + linkage） |

### 常用参数

```bash
# 覆盖已存在工作区
doc-chunk extract bid.docx -o ./out --overwrite

# 分块：章节内最大 token（默认 20000）
doc-chunk chunk ./out --max-tokens 20000

# 强制使用原始目录树（忽略 outline_refined.json）
doc-chunk chunk ./out --use-original

# 回归：仅按 Markdown # 标题分块（v1 行为）
doc-chunk chunk ./out --markdown-headings-only

# 目录优化：宽松校验（默认 strict）
doc-chunk refine ./out -i "合并资质相关章节" --lenient

# 元数据：仅规则分类，不调 LLM
doc-chunk enrich ./out --no-llm

# 流水线：单轮 refine + accept + enrich
doc-chunk pipeline bid.docx -o ./out \
  --run-refine \
  --refine-instruction "合并资质章节" \
  --overwrite
```

### 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 失败 |
| 2 | 部分成功（批量中有失败项） |
| 3 | 参数/工作区错误 |
| 4 | 不支持格式 |

---

## 目录树 LLM 优化（多轮）

在分块前按自然语言调整章节结构；满意后再 `accept` 落盘。

```bash
doc-chunk outline ./output/my-bid

# 第 1 轮：stdout 输出预览 JSON（含 validation.passed）
doc-chunk refine ./output/my-bid -i "把第 3、4 章合并为资质文件"

# 不满意可继续迭代
doc-chunk refine ./output/my-bid -i "附录单独成一级"

# 满意后落盘
doc-chunk refine-accept ./output/my-bid

# 按优化树分块（默认优先 outline_refined.json）
doc-chunk chunk ./output/my-bid
```

需要重新优化时：

```bash
doc-chunk refine-reset ./output/my-bid --force
```

---

## Python API（skills 集成）

```python
from pathlib import Path
from doc_chunk.api import (
    extract_file,
    extract_outline,
    build_tree,
    refine_outline,
    accept_refined_outline,
    chunk_document,
    enrich_chunks,
    run_pipeline,
)
from doc_chunk.convert.blocks_v1 import blocks_to_v1_json

workspace = Path("output/my-bid")

# 分步
extract_file("input/bid.docx", workspace, overwrite=True)
extract_outline(workspace)

preview = refine_outline(workspace, "合并所有资质相关章节")
if preview.validation_passed:
    accept_refined_outline(workspace)

chunk_document(workspace, use_refined=True)
enrich_chunks(workspace, enable_llm_description=False)

# 或一键
run_pipeline(
    Path("input/bid.docx"),
    workspace,
    skip_refine=True,
    skip_enrich=True,
)
```

块 JSON 字段包括：`section_path`、`heading_level`、`outline_source`、`original_node_ids`、`metadata` 等，详见 [`specs/001-document-extract-chunk/contracts/workspace-schemas.md`](specs/001-document-extract-chunk/contracts/workspace-schemas.md)。

---

## LLM 配置

目录优化（`refine`）与元数据描述（`enrich`）需要大模型；提取与分块**不需要**。

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_API_BASE=https://api.openai.com/v1   # 可选，兼容 OpenAI 的网关
export DOC_CHUNK_LLM_MODEL=gpt-4o-mini              # 可选，默认 gpt-4o-mini
```

未配置 API Key 时：`refine` 报错；`enrich` 可用 `--no-llm` 做规则分类。

自定义分类规则（可选）：

```bash
doc-chunk enrich ./out --classification-config ./my_classification.yaml
```

内置类型：`scheme` / `product` / `qualification` / `other`，YAML 格式见 `src/doc_chunk/metadata/default_classification.yaml`。

---

## 行为说明

| 项 | 说明 |
|----|------|
| 目录策略 | TOC/书签 → 标题启发式 → 内容启发式 → 扁平兜底 |
| 章节深度 | 1–8 级 |
| 续切阈值 | 默认 20,000 token/块，章节边界优先 |
| 批量提取 | 单文件失败默认继续，汇总部分成功 |
| 图片 | 仅导出原图；不做 OCR / image_notes |

---

## 开发与测试

```bash
# 全量测试
python -m pytest tests/ -v

# 仅单元/契约
python -m pytest tests/unit tests/contract -v
```

文档索引：

| 文档 | 路径 |
|------|------|
| 完整需求 | [`docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md`](docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md) |
| **tender_knowledge 集成改造** | [`docs/superpowers/specs/2026-06-15-doc-chunk-tender-knowledge-integration.md`](docs/superpowers/specs/2026-06-15-doc-chunk-tender-knowledge-integration.md) |
| 实现计划 | [`docs/superpowers/plans/2026-06-15-doc-chunk.md`](docs/superpowers/plans/2026-06-15-doc-chunk.md) |
| **tk 集成实现计划** | [`docs/superpowers/plans/2026-06-15-doc-chunk-tender-knowledge-integration.md`](docs/superpowers/plans/2026-06-15-doc-chunk-tender-knowledge-integration.md) |
| 验证指南 | [`specs/001-document-extract-chunk/quickstart.md`](specs/001-document-extract-chunk/quickstart.md) |
| CLI 契约 | [`specs/001-document-extract-chunk/contracts/cli.md`](specs/001-document-extract-chunk/contracts/cli.md) |
| Python API | [`specs/001-document-extract-chunk/contracts/python-api.md`](specs/001-document-extract-chunk/contracts/python-api.md) |

---

## 限制（v1）

- 无 Web UI
- 提取阶段无图片 OCR / 视觉 LLM
- 不写入 tender_knowledge 数据库
- PPT 不在首版支持范围
