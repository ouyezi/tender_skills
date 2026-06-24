# doc_chunk

独立 Python 包，将 Word/PDF 标书文档处理为结构化工作区，供 tender_skills 及下游 agent 消费。

**流水线：** 提取 → 目录树 → 文档树 → （可选）LLM 目录优化 → 分块 → 元数据增强

- 支持 `.docx` / `.pdf`（`.doc`、`.docm` 需先转为 `.docx`）
- CLI：`doc-chunk` · 库 API：`doc_chunk.api`
- 输出稳定 JSON schema（`schema_version: 1.0`）
- 分块默认按 **outline 字符锚点**切片，与目录树强一致（无 Heading 样式标书可用）
- Word 表格从 OOXML 物理网格解析，合并单元格去重后写入 `content.md`；完整网格与 LLM 友好文本存于 `tables/` 侧车
- 提取阶段**不做**图片 OCR（`doc_chunk` 仅导出原图；**interpret v2** 在 `tender_insights` 内对引用图片做 OCR）

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
# 1. 提取 → content.md + content.blocks.json + images/ + tables/（docx）
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
├── content.md              # Markdown 正文（表格为去重后的 Markdown）
├── content.blocks.json     # 块索引侧车（char_start/char_end 锚点；table 块含 table_ref）
├── document_tree.json      # 块级文档树（tk DocumentTreeNode 等价）
├── linkage.json            # outline ↔ tree ↔ chunk ID 映射（原始目录分块时生成）
├── images/
│   ├── manifest.json       # 图片清单
│   └── docx-img-001.png
├── tables/                 # 表格侧车（schema 1.1，仅 docx extract）
│   ├── index.json          # block_index → 侧车路径
│   └── t0003.json          # 物理 grid、logical_rows、markdown、llm_text、records
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

`tender-insights interpret` 会在工作区内追加（不修改 `content.md`）：

```text
workspace/
├── interpretation.json     # schema 1.2：overview + 明细 + directory_outline
└── interpret/
    ├── source_content.md   # OCR enrichment 后正文
    └── ocr_cache.json      # 图片 hash → OCR 文本
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

### 表格侧车与 LLM 替换

extract 阶段为每个 Word 表格写入 `tables/t{NNNN}.json`，并在 `content.blocks.json` 对应块上挂 `table_ref`。侧车保留 OOXML 物理网格（`colspan`/`rowspan`/`vmerge`）、去重后的 `logical_rows`、写入 `content.md` 的 `markdown`，以及供 LLM 消费的 `llm_text`（如 `【表格:人员信息】` 结构化记录）。

```python
from pathlib import Path
from doc_chunk.table import load_table_model, substitute_tables_for_llm
from doc_chunk.convert.table_to_docx import render_sidecar_to_docx
from doc_chunk.models.content_block import ContentBlocksFile
from doc_chunk.workspace.layout import OutputWorkspace
from docx import Document

workspace = OutputWorkspace(Path("output/my-bid"))
blocks = ContentBlocksFile.model_validate_json(
    workspace.content_blocks_path.read_text(encoding="utf-8")
)
content_md = workspace.content_path.read_text(encoding="utf-8")

# 将区间内 Markdown 表格替换为 llm_text（无侧车时透传原文）
llm_input = substitute_tables_for_llm(content_md, blocks, workspace=workspace)

# 从侧车回写 Word（可选修改 records 后渲染）
sidecar = load_table_model(workspace, "tables/t0003.json")
doc = Document()
render_sidecar_to_docx(doc, sidecar, records=sidecar.records)
doc.save("out.docx")
```

旧工作区无 `tables/` 时，`substitute_tables_for_llm` 保持 Markdown 不变（向后兼容）。

---

## LLM 配置

目录优化（`refine`）与元数据 LLM 描述（`enrich` 默认开启时）需要大模型；**提取、目录树、文档树、分块不需要**。

与 `tender_knowledge` 共用环境变量（默认 **千问 Qwen** 兼容 OpenAI 接口）：

```bash
export LLM_PROVIDER=qwen
export LLM_API_KEY=sk-...
export LLM_BASE_URL=                    # 留空则用 DashScope 兼容端点
export LLM_MODEL=qwen3.6-plus           # 留空则 qwen-plus
```

或复制 `tender_knowledge/.env` 后 `set -a && source .env && set +a`。

| 变量 | 默认（`LLM_PROVIDER=qwen`） |
|------|---------------------------|
| `LLM_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `LLM_MODEL` | `qwen-plus` |

仍支持旧变量：`OPENAI_API_KEY`、`OPENAI_API_BASE`、`DOC_CHUNK_LLM_MODEL`。

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
| 图片 | 仅导出原图到 `images/`；OCR 由 `tender-insights interpret` 可选处理（默认开启） |
| Word 表格 | 从 OOXML 解析物理网格，合并单元格去重后写入 `content.md`；完整结构写入 `tables/` 侧车（`llm_text` + `records`） |
| 表格回写 | `render_table_to_docx` / `render_sidecar_to_docx` 按物理网格与 `records` 写回 `.docx` |

---

## tender_insights（招标语义分析）

在 `doc_chunk` 工作区之上，`tender_insights` 包提供招标业务语义分析：解读（废标/得分/投标风险/目录 + 概要）、模版提取、法务审核。解读产出 `interpretation.json`（**schema 1.2**），供 agent 与下游系统消费。

**设计文档：**

- v1 总览：[`docs/superpowers/specs/2026-06-16-tender-insights-skills-design.md`](docs/superpowers/specs/2026-06-16-tender-insights-skills-design.md)
- **interpret v2**：[`docs/superpowers/specs/2026-06-24-interpret-v2-design.md`](docs/superpowers/specs/2026-06-24-interpret-v2-design.md) · [实现计划](docs/superpowers/plans/2026-06-24-interpret-v2.md)

### interpret v2 要点

| 项 | 说明 |
|----|------|
| 覆盖范围 | **全文分段**提取，不再依赖章节标题关键词路由 |
| 分段策略 | 优先复用 `chunks/`；在 2k–12k tokens 间 merge/split，保证逻辑完整 |
| LLM 调用 | 每段 **1 次**（固定 system prompt，一次返回四类明细）；合并后再 **1 次**生成概要 |
| 概要 + 明细 | `overview`（维度摘要）+ `disqualification_items` / `scoring_items` / `bid_risk_items` / `directory_requirements` |
| 目录格式 | `directory_outline`（树形，供下游目录生成）+ `directory_requirements.structure` |
| 图片 OCR | 对 `content.md` 引用的图片调用 **qwen-vl-ocr**（hash 缓存、logo 跳过、大图压缩）；**不修改** `content.md` |
| 边界 | 只改 `tender_insights`；`doc_chunk` 工作区只读 |

### 安装

与 `doc_chunk` 共用同一虚拟环境：

```bash
cd tender_skills
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

验证：

```bash
tender-insights --help
python -m pytest tests/tender_insights/ -v
```

### 快速开始

输入支持 **工作区目录** 或 **原始 `.docx`/`.pdf`**（后者自动调用 `doc-chunk pipeline`）。

```bash
# 解读：废标项、得分项、投标风险、目录要求
.venv/bin/tender-insights interpret /path/to/bid.docx \
  -o ./output/my-bid \
  --overwrite

# 模版：承诺书、授权书、声明函等
.venv/bin/tender-insights template ./output/my-bid

# 法务：合规风险 + 待确认事项（独立于 interpret）
.venv/bin/tender-insights legal ./output/my-bid

# 一次性跑 interpret + template + legal
.venv/bin/tender-insights all /path/to/bid.docx -o ./output/my-bid --overwrite
```

### 产出文件

| 命令 | 产物 | 说明 |
|------|------|------|
| `interpret` | `interpretation.json` | schema **1.1**：概要 `overview`、四类明细、`directory_outline` |
| `interpret` | `interpret/source_content.md` | OCR enrichment 后正文（锚点基准；不覆盖 `content.md`） |
| `interpret` | `interpret/ocr_cache.json` | 图片 SHA256 → OCR 文本缓存 |
| `template` | `templates/index.json` + `templates/*.md` | 嵌入正文模版切片 |
| `legal` | `legal_review.json` | `risk_items`（法务合规）+ `pending_confirmations` |

工作区 `manifest.json` 会追加对应 `stages` 与 `outputs` 条目。

#### `interpretation.json` 主要字段（1.1）

| 字段 | 说明 |
|------|------|
| `overview.summary` | 整份标书解读概要 |
| `overview.*_summary` | 废标 / 得分 / 投标风险 / 目录 各维度摘要 |
| `disqualification_items` | 废标项明细 |
| `scoring_items` | 得分项明细 |
| `bid_risk_items` | 投标视角风险明细 |
| `directory_requirements` | 目录/文件组成要求（含可选 `structure` 树） |
| `directory_outline` | 推荐目录树（`nodes[]`，供下游目录生成） |
| `segment_count` | 全文分段数 |
| `ocr_image_count` | OCR API 实际调用次数 |

> **风险字段区分：** `interpretation.json` 的 `bid_risk_items` 是投标执行视角；`legal_review.json` 的 `risk_items` 是法务合规视角。两套分析独立运行，互不读取。

切片送 LLM 前，`interpret` 会：① 对 `content.md` 引用图片做 OCR 写入 `interpret/source_content.md`；② 通过 `slice_for_llm` 将 Markdown 表格替换为侧车 `llm_text`。无 `tables/` 侧车时仍使用正文原文。

### LLM 配置

解读与法务阶段需要大模型；模版分类以规则为主。**interpret v2** 默认使用 **千问（Qwen）** 做文本解读，OCR 默认 **qwen-vl-ocr**：

```bash
export LLM_PROVIDER=qwen
export LLM_API_KEY=sk-...
export LLM_BASE_URL=                    # 留空 → DashScope 兼容端点
export LLM_MODEL=qwen3.6-plus           # 文本解读模型

# interpret v2 OCR / 分段（可选）
export OCR_ENABLED=true                 # 设为 false 跳过 OCR
export OCR_MODEL=qwen-vl-ocr
export SEGMENT_MIN_TOKENS=2000
export SEGMENT_MAX_TOKENS=12000
```

可与 `tender_knowledge` 共用同一 `.env`（`LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL`）。

| 变量 | 默认 | 说明 |
|------|------|------|
| `OCR_ENABLED` | `true` | 是否对 `content.md` 引用图片做 OCR |
| `OCR_MODEL` | `qwen-vl-ocr` | 视觉 OCR 模型 |
| `SEGMENT_MIN_TOKENS` | `2000` | 过小分段合并阈值 |
| `SEGMENT_MAX_TOKENS` | `12000` | 单段送 LLM 上限 |
| `OCR_LOGO_MAX_BYTES` | `10240` | ≤ 此大小且宽/高 < 128px 视为 logo，跳过 OCR |
| `OCR_MAX_LONG_EDGE` | `1500` | OCR 前图片长边压缩上限（像素） |

### Python API

```python
from pathlib import Path
from tender_insights.api import (
    resolve_workspace_path,
    interpret_document,
    extract_templates,
    review_legal,
)

ws = resolve_workspace_path(
    Path("/path/to/bid.docx"),
    output_dir=Path("./output/my-bid"),
    overwrite=True,
)
interpret_document(ws)
extract_templates(ws)
review_legal(ws)
```

测试时可注入 `FakeLLMClient`（见 `doc_chunk.llm.client`）。

### Cursor Skills 索引

| Skill | 路径 | CLI |
|-------|------|-----|
| 提取 | [`.cursor/skills/tender-extract/SKILL.md`](.cursor/skills/tender-extract/SKILL.md) | `doc-chunk pipeline` |
| 解读 | [`.cursor/skills/tender-interpret/SKILL.md`](.cursor/skills/tender-interpret/SKILL.md) | `tender-insights interpret` |
| 模版 | [`.cursor/skills/tender-template/SKILL.md`](.cursor/skills/tender-template/SKILL.md) | `tender-insights template` |
| 法务 | [`.cursor/skills/tender-legal-review/SKILL.md`](.cursor/skills/tender-legal-review/SKILL.md) | `tender-insights legal` |

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
| **Word 表格提取（004）** | [`docs/superpowers/specs/2026-06-17-docx-table-extract-design.md`](docs/superpowers/specs/2026-06-17-docx-table-extract-design.md) |
| **tender_insights interpret v2** | [`docs/superpowers/specs/2026-06-24-interpret-v2-design.md`](docs/superpowers/specs/2026-06-24-interpret-v2-design.md) |

---

## Viewer（调试 UI）

独立附属应用 `viewer/`，供本机上传/打开工作区、浏览 outline 树与章节 Markdown（左侧目录 + 右侧原文）。Outline 父节点支持展开/收起，便于浏览深层目录。

```bash
pip install -e "./viewer[dev]"
python -m viewer
# → http://127.0.0.1:8765
```

详见 [`viewer/README.md`](viewer/README.md)。

---

## 限制（v1）

- 无生产级 Web UI（仅有本机调试 viewer）
- `doc_chunk` 提取阶段无图片 OCR（interpret v2 在 `tender_insights` 内对引用图片做 OCR）
- 不写入 tender_knowledge 数据库
- `.doc` / `.docm` 不直接提取，需先转为 `.docx`
- PPT 不在首版支持范围
- interpret 暂不支持多文件工作区合并分析；zip 附件包模版不在范围
