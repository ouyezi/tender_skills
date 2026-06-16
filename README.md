# doc_chunk

独立 Python 包，将 Word/PDF 标书文档处理为结构化工作区，供 tender_skills 及下游 agent 消费。

**流水线：** 提取 → 目录树 → 文档树 → （可选）LLM 目录优化 → 分块 → 元数据增强

- 支持 `.docx` / `.pdf`（`.doc`、`.docm` 需先转为 `.docx`）
- CLI：`doc-chunk` · 库 API：`doc_chunk.api`
- 输出稳定 JSON schema（`schema_version: 1.0`）
- 分块默认按 **outline 字符锚点**切片，与目录树强一致（无 Heading 样式标书可用）
- 提取阶段**不做**图片 OCR（图像语义由下游 skills 处理）

完整需求见 [`docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md`](docs/superpowers/specs/2026-06-15-doc-chunk-requirements.md)。  
**tender_knowledge 集成**见 [`docs/superpowers/specs/2026-06-15-doc-chunk-tender-knowledge-integration.md`](docs/superpowers/specs/2026-06-15-doc-chunk-tender-knowledge-integration.md)。  
**集成修复（003，已实现）**见 [`docs/superpowers/specs/2026-06-15-doc-chunk-tk-integration-fixes.md`](docs/superpowers/specs/2026-06-15-doc-chunk-tk-integration-fixes.md)。

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

默认执行：提取 → 目录树 → 文档树 → 分块 → **规则分类**（不调 LLM 描述）。  
目录优化默认跳过；元数据增强默认开启但仅用 YAML 规则，无需 API Key。

```bash
doc-chunk pipeline /path/to/bid.docx \
  -o ./output/my-bid \
  --overwrite
```

若只要最短路径、跳过元数据：

```bash
doc-chunk pipeline /path/to/bid.docx \
  -o ./output/my-bid \
  --overwrite \
  --skip-enrich
```

### 分步执行

```bash
# 1. 提取 → content.md + content.blocks.json + images/
doc-chunk extract /path/to/bid.docx -o ./output/my-bid

# 无 Word Heading 样式时，可将编号行升格为 Markdown # 标题（便于人工阅读）
doc-chunk extract /path/to/bid.docx -o ./output/my-bid --promote-headings auto

# 2. 目录树 → outline.json（自动写入 char 锚点）
doc-chunk outline ./output/my-bid

# 3. 块级文档树 → document_tree.json（tender_knowledge DocumentTreeNode 等价）
doc-chunk tree ./output/my-bid

# 4. 分块 → chunks/（默认按 outline 锚点切片）
doc-chunk chunk ./output/my-bid

# 5. 元数据（可选，需 LLM 或使用 --no-llm 仅规则分类）
doc-chunk enrich ./output/my-bid --no-llm
```

### 真实样例

已对 621MB 餐补标书跑通：

```bash
doc-chunk pipeline \
  "/path/to/【2中银保险上海分公司】餐补标书.docx" \
  -o ./output/zhongyin-canbu \
  --overwrite \
  --skip-enrich
```

典型产出：616 张图片、173 个目录节点、174 个 chunk，约 3 秒（不含 LLM）。

---

## 工作区结构

每次处理在 `-o` 指定目录生成：

```text
workspace/
├── content.md              # Markdown 正文
├── content.blocks.json     # 块索引侧车（char_start/char_end 锚点）
├── document_tree.json      # 块级文档树（tk DocumentTreeNode 等价）
├── linkage.json            # outline ↔ tree ↔ chunk ID 映射（原始目录分块时生成）
├── images/
│   ├── manifest.json       # 图片清单
│   └── docx-img-001.png
├── outline.json            # 原始目录树（含 char 锚点）
├── outline_refined.json    # LLM 优化后（accept 后才有）
├── outline_mapping.json    # 优化节点 → 原文映射
├── outline_refine_summary.md
├── chunks/
│   ├── index.json          # 块索引（含 primary_outline_node_id 等）
│   └── chunk-0001.json     # 单块（markdown + blocks + original_node_ids）
├── manifest.json           # 阶段状态与产物路径
└── logs/
```

---

## tender_knowledge 对接要点

| 能力 | 产物 / 行为 |
|------|-------------|
| outline 与 chunk 强一致 | `outline` 阶段用 `content.blocks.json` 补全 `anchor.char_start`；`chunk` 默认走锚点切片 |
| 块级文档树 | `document_tree.json`，由 `tree` 或 `pipeline` 自动生成 |
| blocks_v1 等价正文 | 每个 `chunk-*.json` 含 `blocks[]`（paragraph / table / image） |
| ID 三联映射 | `linkage.json` + `chunks/index.json` 中的 `primary_outline_node_id`、`document_tree_node_id` |
| 进度回调 | `run_pipeline(..., on_progress=fn)` 供长任务汇报 |

消费方只需薄适配层读取工作区 JSON，**不写入** tender_knowledge 数据库。详见集成规格文档。

**003 集成修复**：`document_tree` 节点 ID 唯一、outline→tree heading 全覆盖、linkage 全覆盖与 `document_tree_node_id` 三联映射。见 [tk 集成修复规格](docs/superpowers/specs/2026-06-15-doc-chunk-tk-integration-fixes.md)。

---

## CLI 命令参考

| 命令 | 说明 |
|------|------|
| `extract INPUT -o DIR` | 提取单文件；`INPUT` 为目录时批量处理 |
| `outline WORKSPACE` | 从 `content.md` 生成 `outline.json` 并补全锚点 |
| `tree WORKSPACE` | 生成 `document_tree.json` |
| `refine WORKSPACE -i "指令"` | LLM 优化目录树（预览，不落盘） |
| `refine-accept WORKSPACE` | 确认并写入 `outline_refined.json` 等 |
| `refine-discard WORKSPACE` | 放弃当前 refine session |
| `refine-reset WORKSPACE` | 清除已 accept 的优化结果，重新开始 |
| `chunk WORKSPACE` | 按 outline 锚点分块（默认）；有 refined 时优先 refined |
| `enrich WORKSPACE` | 块描述 + 分类 |
| `pipeline INPUT -o DIR` | 端到端串联（extract → outline → tree → chunk → enrich） |

### 常用参数

```bash
# 覆盖已存在工作区
doc-chunk extract bid.docx -o ./out --overwrite

# 无 Heading 样式：升格编号行为 Markdown 标题
doc-chunk extract bid.docx -o ./out --promote-headings auto

# 分块：章节内最大 token（默认 20000）
doc-chunk chunk ./out --max-tokens 20000

# 强制使用原始目录树（忽略 outline_refined.json）
doc-chunk chunk ./out --use-original

# 回归：仅按 Markdown # 标题分块（v1 行为，需 outline 无 char 锚点才与锚点模式不同）
doc-chunk chunk ./out --markdown-headings-only

# 目录优化：宽松校验（默认 strict）
doc-chunk refine ./out -i "合并资质相关章节" --lenient

# 元数据：仅规则分类，不调 LLM
doc-chunk enrich ./out --no-llm

# 流水线：单轮 refine + accept；enrich 默认规则分类（无 API Key）
doc-chunk pipeline bid.docx -o ./out \
  --run-refine \
  --refine-instruction "合并资质章节" \
  --overwrite

# 流水线：跳过元数据
doc-chunk pipeline bid.docx -o ./out --skip-enrich --overwrite
```

### 餐补可选回归（003 / NF1）

```bash
export DOC_CHUNK_CANBU_FIXTURE=/path/to/canbu.docx
export DOC_CHUNK_CANBU_T_BASE=120   # main 分支 3 次 pipeline 中位数（秒）
.venv/bin/python -m pytest tests/integration/test_canbu_regression.py -v -s
```

未设置 `DOC_CHUNK_CANBU_FIXTURE` 时集成测试自动 skip。

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
doc-chunk tree ./output/my-bid

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

> 使用 refined 目录分块时，切片依据 `outline_mapping.json` 的 `markdown_range`；`linkage.json` 仅在原始 outline 分块路径下生成。

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

def on_progress(stage: str, payload: dict) -> None:
    print(stage, payload.get("message", ""))

workspace = Path("output/my-bid")

# 分步
extract_file("input/bid.docx", workspace, overwrite=True, promote_headings="auto")
extract_outline(workspace)
build_tree(workspace)

preview = refine_outline(workspace, "合并所有资质相关章节")
if preview.validation_passed:
    accept_refined_outline(workspace)

chunk_document(workspace, use_refined=True, on_progress=on_progress)
enrich_chunks(workspace, enable_llm_description=False)

# 或一键（默认 skip_refine=True；enrich 为规则分类、不调 LLM 描述）
run_pipeline(
    Path("input/bid.docx"),
    workspace,
    overwrite=True,
    skip_refine=True,
    skip_enrich=False,
    on_progress=on_progress,
)
```

块 JSON 关键字段：`section_path`、`heading_level`、`outline_source`、`original_node_ids`、`blocks`、`source_ranges`、`metadata` 等，详见 [`specs/001-document-extract-chunk/contracts/workspace-schemas.md`](specs/001-document-extract-chunk/contracts/workspace-schemas.md)。

---

## LLM 配置

目录优化（`refine`）与元数据 LLM 描述（`enrich` 默认开启时）需要大模型；**提取、目录树、文档树、分块不需要**。

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_API_BASE=https://api.openai.com/v1   # 可选，兼容 OpenAI 的网关
export DOC_CHUNK_LLM_MODEL=gpt-4o-mini              # 可选，默认 gpt-4o-mini
```

| 场景 | 无 API Key 时 |
|------|----------------|
| `refine` | 报错退出 |
| `enrich` | 使用 `--no-llm` 做规则分类 |
| `pipeline`（默认） | 可正常运行：跳过 refine，enrich 仅规则分类 |

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
| 锚点补全 | `outline` 阶段读取 `content.blocks.json`，为节点写入 `char_start`/`char_end` |
| 分块策略 | 有 char 锚点时按锚点切片（默认）；否则按 Markdown `#` 标题；`--markdown-headings-only` 强制标题模式 |
| 章节深度 | 1–8 级 |
| 续切阈值 | 默认 20,000 token/块，章节边界优先 |
| 批量提取/流水线 | 单文件失败默认继续，汇总部分成功（退出码 2） |
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
| **tk 集成修复（003）** | [`docs/superpowers/specs/2026-06-15-doc-chunk-tk-integration-fixes.md`](docs/superpowers/specs/2026-06-15-doc-chunk-tk-integration-fixes.md) |
| 实现计划 | [`docs/superpowers/plans/2026-06-15-doc-chunk.md`](docs/superpowers/plans/2026-06-15-doc-chunk.md) |
| **tk 集成实现计划** | [`docs/superpowers/plans/2026-06-15-doc-chunk-tender-knowledge-integration.md`](docs/superpowers/plans/2026-06-15-doc-chunk-tender-knowledge-integration.md) |
| **tk 集成修复计划（003）** | [`docs/superpowers/plans/2026-06-15-doc-chunk-tk-integration-fixes.md`](docs/superpowers/plans/2026-06-15-doc-chunk-tk-integration-fixes.md) |
| 验证指南 | [`specs/001-document-extract-chunk/quickstart.md`](specs/001-document-extract-chunk/quickstart.md) |
| CLI 契约 | [`specs/001-document-extract-chunk/contracts/cli.md`](specs/001-document-extract-chunk/contracts/cli.md) |
| Python API | [`specs/001-document-extract-chunk/contracts/python-api.md`](specs/001-document-extract-chunk/contracts/python-api.md) |
| 工作区 Schema | [`specs/001-document-extract-chunk/contracts/workspace-schemas.md`](specs/001-document-extract-chunk/contracts/workspace-schemas.md) |

---

## Viewer（调试 UI）

独立附属应用 `viewer/`，供本机上传/打开工作区、浏览 outline 树与章节 Markdown（左侧目录 + 右侧原文）。

```bash
pip install -e "./viewer[dev]"
python -m viewer
# → http://127.0.0.1:8765
```

详见 [`viewer/README.md`](viewer/README.md)。

---

## 限制（v1）

- 无生产级 Web UI（仅有本机调试 viewer）
- 提取阶段无图片 OCR / 视觉 LLM
- 不写入 tender_knowledge 数据库
- `.doc` / `.docm` 不直接提取，需先转为 `.docx`
- PPT 不在首版支持范围
