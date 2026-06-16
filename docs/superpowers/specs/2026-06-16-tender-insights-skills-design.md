# 设计规格：招标语义分析 Skills 与 tender_insights 包

**版本**: 1.0  
**日期**: 2026-06-16  
**状态**: 待评审  
**Feature ID**: `005-tender-insights-skills`  
**建议分支 / worktree**: `005-tender-insights-skills`

---

## 1. 概述

在现有 `doc_chunk` 文档提取能力之上，新增 Python 包 **`tender_insights`** 及四个 Cursor Skills，覆盖招标文件的：

1. **提取** — 转 Markdown、导出图片（复用 `doc_chunk`）
2. **解读** — 废标项、得分项、风险点（投标视角）、目录要求
3. **模版** — 嵌入正文中的特定提交模版（如承诺书、授权书）
4. **法务审核** — 风险点（合规视角）、待确认事项

**核心原则**：`doc_chunk` 负责结构与锚点；`tender_insights` 负责招标业务语义；Skills 为薄封装，调用 CLI/API 并说明契约。

---

## 2. 已确认的设计决策

| 决策点 | 选择 | 说明 |
|--------|------|------|
| 输入边界 | **混合模式 C** | 提取 skill 产出工作区；解读/模版/法务既接受工作区，也接受原始 `.docx`/`.pdf`（内部自动 `doc_chunk pipeline`） |
| 解读 vs 法务 | **完全独立 C** | 两套分析从零独立运行，不共享提取结果文件；可共享基础设施（工作区加载、LLM、锚点工具） |
| 模版含义 | 特定提交内容模版 | 招标文件要求的承诺书、授权书、声明函等格式样例 |
| 模版来源 | **嵌入正文 A** | 模版位于主文档章节内（如「附件：承诺书格式」），非独立附件文件 |
| 解读产出粒度 | **结构化 C** | 类型 + 摘要 + 原文摘录 + 章节路径 + char 锚点 + 业务字段（分值、严重度、触发条件等） |
| 法务产出粒度 | **方案 A** | 风险点含描述/条款/类型/等级/锚点；待确认事项含描述/确认方/建议确认内容 |

---

## 3. 架构

### 3.1 组件关系

```text
输入
├── 原始 docx/pdf
└── doc_chunk 工作区

        ↓
WorkspaceResolver（无工作区时自动 doc_chunk pipeline）
        ↓
┌───────────────┬────────────────┬────────────────┐
│ interpret     │ template       │ legal          │
│ 解读分析       │ 模版提取        │ 法务审核        │
└───────────────┴────────────────┴────────────────┘
        ↓
工作区扩展产物
├── interpretation.json
├── templates/index.json + templates/*.md
└── legal_review.json
```

### 3.2 包边界

| 包 | 职责 | 不做 |
|----|------|------|
| `doc_chunk` | 提取、目录树、分块、锚点、规则分类 | 招标语义、合规判断 |
| `tender_insights` | 招标语义提取、结构化 JSON 产出 | 替换 doc_chunk 提取逻辑 |
| Cursor Skills | 触发词、命令示例、输出说明、用户呈现指引 | 重业务逻辑 |

### 3.3 推荐方案（已批准）

采用 **独立 Python 包 `tender_insights`**（非薄 prompt-only，非塞入 doc_chunk pipeline）。

理由：

- 与 `doc_chunk` Out of Scope（合规诊断、图像语义）一致
- 稳定 JSON schema + 锚点 + 回归测试
- 解读/法务独立，共享基础设施不共享分析结果

---

## 4. Skills 与代码映射

| Skill 名称 | 代码 | CLI | 输入 | 产出 |
|------------|------|-----|------|------|
| `tender-extract` | `doc_chunk` | `doc-chunk pipeline` | `.docx`/`.pdf` | 标准工作区 |
| `tender-interpret` | `tender_insights.interpret` | `tender-insights interpret` | 工作区或原始文件 | `interpretation.json` |
| `tender-template` | `tender_insights.template` | `tender-insights template` | 工作区或原始文件 | `templates/` |
| `tender-legal-review` | `tender_insights.legal` | `tender-insights legal` | 工作区或原始文件 | `legal_review.json` |

Skills 放置路径（实现阶段）：`.cursor/skills/tender-extract/` 等。

---

## 5. 共享基础设施（`tender_insights/common/`）

### 5.1 WorkspaceResolver

- 输入：`Path`（工作区目录或原始文件）
- 判定：存在 `manifest.json` + `content.md` → 视为工作区；否则视为原始文件
- 原始文件：调用 `doc_chunk.api.run_pipeline(..., skip_refine=True, skip_enrich=False)` 生成工作区
- 输出：已验证的 `OutputWorkspace` 等价句柄（可复用 `doc_chunk.workspace.layout` 或薄封装）

### 5.2 SectionRouter

- 读取 `outline.json` + `chunks/index.json`
- 按 YAML 路由规则将章节节点分配给各分析器
- 示例路由目标：`评标办法`、`投标人须知`、`合同条款`、`附件`

### 5.3 AnchorBackfill

- 输入：LLM 返回的 `source_excerpt` + 全文 `content.md`
- 输出：`char_start`、`char_end`（模糊匹配 + 最长公共子串兜底）
- 失败时：`char_start`/`char_end` 为 `null`，保留 `section_path`

### 5.4 LLMExtractor

- 复用 `doc_chunk.llm.LLMClient` 协议
- 统一 `response_format=json`、重试 ≤2 次、Pydantic 校验失败时重试
- 环境变量与 `doc_chunk` 一致：`OPENAI_API_KEY`、`OPENAI_API_BASE`、`DOC_CHUNK_LLM_MODEL`

### 5.5 OutputWriter

- 写入分析产物到工作区子路径
- 更新 `manifest.json` 的 `stages` 与 `outputs`
- `schema_version: "1.0"` 写入各 JSON 顶层

---

## 6. 解读模块（`tender_insights/interpret/`）

### 6.1 产出文件：`interpretation.json`

```json
{
  "schema_version": "1.0",
  "source_workspace": "...",
  "analyzed_at": "ISO8601",
  "disqualification_items": [],
  "scoring_items": [],
  "bid_risk_items": [],
  "directory_requirements": []
}
```

### 6.2 数据模型

#### DisqualificationItem（废标项）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✓ | 稳定 ID，如 `dq-001` |
| `title` | string | ✓ | 简短标题 |
| `summary` | string | ✓ | 摘要 |
| `trigger_condition` | string | ✓ | 触发废标的条件 |
| `source_excerpt` | string | ✓ | 原文摘录 |
| `section_path` | string[] | ✓ | 章节路径 |
| `char_start` | int \| null | | 锚点起始 |
| `char_end` | int \| null | | 锚点结束 |
| `confidence` | float | ✓ | 0–1 |

#### ScoringItem（得分项）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✓ | 如 `sc-001` |
| `title` | string | ✓ | |
| `summary` | string | ✓ | |
| `max_score` | float \| null | | 分值 |
| `weight` | string \| null | | 权重描述（如「30%」） |
| `criteria` | string | ✓ | 评分标准摘要 |
| `source_excerpt` | string | ✓ | |
| `section_path` | string[] | ✓ | |
| `char_start` / `char_end` | int \| null | | |
| `confidence` | float | ✓ | |

#### BidRiskItem（风险点 — 投标视角）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✓ | 如 `br-001` |
| `title` | string | ✓ | |
| `summary` | string | ✓ | |
| `severity` | enum | ✓ | `high` / `medium` / `low` |
| `risk_category` | string | ✓ | 如 `资质`、`商务`、`技术` |
| `source_excerpt` | string | ✓ | |
| `section_path` | string[] | ✓ | |
| `char_start` / `char_end` | int \| null | | |
| `confidence` | float | ✓ | |

#### DirectoryRequirement（目录要求）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✓ | 如 `dr-001` |
| `title` | string | ✓ | |
| `required_sections` | string[] | ✓ | 要求的章节/材料清单 |
| `mandatory` | bool | ✓ | 是否强制 |
| `source_excerpt` | string | ✓ | |
| `section_path` | string[] | ✓ | |
| `char_start` / `char_end` | int \| null | | |
| `confidence` | float | ✓ | |

### 6.3 实现组件

| 文件 | 职责 |
|------|------|
| `models.py` | Pydantic 模型 |
| `routing.yaml` | 章节路由关键词（评标、须知、格式要求等） |
| `prompts.py` | 分类型 system/user prompt 模板 |
| `extractor.py` | 路由 → 选 chunk → LLM → 校验 → 锚点回填 |
| `merger.py` | 跨 chunk 去重（标题 + 摘录相似度） |
| `cli.py` | `tender-insights interpret WORKSPACE_OR_FILE` |

### 6.4 处理流程

1. `SectionRouter` 选出与废标/得分/目录相关的 outline 节点及对应 chunks
2. 按类型分批调用 LLM（每批 ≤ N chunks，控制 token）
3. Pydantic 解析；校验失败重试
4. `AnchorBackfill` 回填锚点
5. `merger` 去重合并
6. 写入 `interpretation.json`，更新 manifest

---

## 7. 模版模块（`tender_insights/template/`）

### 7.1 产出结构

```text
workspace/templates/
├── index.json
├── commitment-001.md
├── authorization-001.md
└── ...
```

### 7.2 `templates/index.json`

```json
{
  "schema_version": "1.0",
  "templates": [
    {
      "id": "tpl-001",
      "type": "commitment",
      "type_label": "承诺书",
      "title": "投标人诚信承诺书",
      "section_path": ["附件", "承诺书格式"],
      "file": "templates/commitment-001.md",
      "char_start": 120340,
      "char_end": 122100,
      "confidence": 0.92
    }
  ]
}
```

### 7.3 模版类型枚举（v1）

| `type` | `type_label` | 识别关键词示例 |
|--------|--------------|----------------|
| `commitment` | 承诺书 | 承诺书、诚信承诺 |
| `authorization` | 授权书 | 授权书、授权委托 |
| `declaration` | 声明函 | 声明函、声明书 |
| `other` | 其他 | 兜底 |

### 7.4 实现组件

| 文件 | 职责 |
|------|------|
| `detector.py` | 在 outline 中匹配附件/模版章节 |
| `boundary.py` | 确定模版 Markdown 起止（同级下一标题或 chunk 边界） |
| `extractor.py` | 切片写入 `templates/*.md` |
| `classifier.py` | LLM 辅助分类 `type`（规则优先，LLM 兜底） |
| `cli.py` | `tender-insights template WORKSPACE_OR_FILE` |

### 7.5 处理流程

1. outline 节点匹配：`附件`、`承诺书`、`授权`、`声明` 等
2. 无明确节点时，对标题含关键词的 chunk 做全文扫描
3. 边界切分 → 写入独立 `.md`
4. 生成 `index.json`，更新 manifest

---

## 8. 法务模块（`tender_insights/legal/`）

### 8.1 产出文件：`legal_review.json`

```json
{
  "schema_version": "1.0",
  "source_workspace": "...",
  "analyzed_at": "ISO8601",
  "risk_items": [],
  "pending_confirmations": []
}
```

**独立于 `interpretation.json`**，不复用解读结果。

### 8.2 数据模型

#### LegalRiskItem

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✓ | 如 `lr-001` |
| `description` | string | ✓ | 风险描述 |
| `clause_excerpt` | string | ✓ | 涉及条款原文 |
| `risk_type` | string | ✓ | 违约/知识产权/付款/争议解决等 |
| `severity` | enum | ✓ | `high` / `medium` / `low` |
| `section_path` | string[] | ✓ | |
| `char_start` / `char_end` | int \| null | | |
| `confidence` | float | ✓ | |

#### PendingConfirmation

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✓ | 如 `pc-001` |
| `description` | string | ✓ | 待确认问题描述 |
| `confirm_with` | string | ✓ | 甲方/法务/业务 |
| `suggested_question` | string | ✓ | 建议向对方确认的内容 |
| `section_path` | string[] | ✓ | |
| `char_start` / `char_end` | int \| null | | |
| `confidence` | float | ✓ | |

### 8.3 实现组件

| 文件 | 职责 |
|------|------|
| `models.py` | Pydantic 模型 |
| `routing.yaml` | 合同条款、通用条款、付款、违约责任等路由 |
| `prompts.py` | 法务视角独立 prompt（强调合规、条款不对等） |
| `extractor.py` | 独立 pipeline |
| `cli.py` | `tender-insights legal WORKSPACE_OR_FILE` |

---

## 9. CLI 设计

**入口**：`tender-insights`（console script）

| 子命令 | 说明 |
|--------|------|
| `interpret PATH` | 解读分析 |
| `template PATH` | 模版提取 |
| `legal PATH` | 法务审核 |
| `all PATH` | 依次运行 interpret + template + legal（便利命令，非必须） |

### 通用参数

| 参数 | 说明 |
|------|------|
| `-o, --output DIR` | 工作区目录（输入为原始文件时必填；输入为工作区时可省略） |
| `--overwrite` | 覆盖已有分析产物 |
| `--no-llm` | 仅规则/启发式（模版检测可用；解读/法务质量下降，用于测试） |
| `--llm-model MODEL` | 覆盖默认模型 |

### 退出码

与 `doc_chunk` 对齐：`0` 成功、`1` 失败、`3` 参数错误。

---

## 10. Python API（skills 集成）

```python
from pathlib import Path
from tender_insights.api import (
    resolve_workspace,
    interpret_document,
    extract_templates,
    review_legal,
)

workspace = resolve_workspace(Path("bid.docx"), output_dir=Path("output/bid"))
interpret_document(workspace)
extract_templates(workspace)
review_legal(workspace)
```

---

## 11. 实施阶段

| Phase | 内容 | 产出 |
|-------|------|------|
| **0** | worktree `005-tender-insights-skills`、包脚手架、`WorkspaceResolver` | 可 install 的空包 + 测试 |
| **1** | 提取 skill 文档化 | `tender-extract/SKILL.md`（无新代码） |
| **2** | `interpret`：废标项 + 得分项优先 | `interpretation.json` + 单元/集成测试 |
| **3** | `interpret`：风险点 + 目录要求 | 完整解读模块 |
| **4** | `template` | `templates/` + skill |
| **5** | `legal` | `legal_review.json` + skill |
| **6** | 样例标书回归 + 四 skills 定稿 | 餐补标书或同类 fixture |

---

## 12. 测试策略

| 层级 | 范围 |
|------|------|
| 单元 | Pydantic 模型、AnchorBackfill、SectionRouter、TemplateDetector |
| 契约 | `interpretation.json`、`legal_review.json`、`templates/index.json` schema |
| 集成 | 餐补标书 fixture：pipeline → interpret → 断言条目数下限与关键字段存在 |
| 回归 | 同 fixture 多次运行产出结构稳定（允许 LLM 文本差异，结构字段必存在） |

---

## 13. 非目标（v1 Out of Scope）

- 图片 OCR / 扫描件模版识别
- 独立附件文件包（`.zip` 内多文件）的模版识别
- 与 tender_knowledge 数据库写入
- 自动撰写投标应答内容
- 解读与法务结果的自动交叉引用或合并视图
- Web UI（继续用 `viewer` 浏览工作区，不做法务/解读专用 UI）

---

## 14. 依赖

| 依赖 | 用途 |
|------|------|
| `doc_chunk`（同仓库 editable） | pipeline、工作区、LLM 客户端 |
| `pydantic` v2 | 数据模型 |
| `typer` | CLI |
| `pyyaml` | 路由规则配置 |
| LLM API | interpret / template 分类 / legal |

---

## 15. 风险与缓解

| 风险 | 缓解 |
|------|------|
| LLM 幻觉漏项 | 分 chunk 提取 + 路由缩小范围；集成测试设条目下限 |
| 锚点回填失败 | 保留 `section_path`；`char_*` 允许 null |
| 长文档 token 超限 | 按 outline chunk 分批，不送全文 |
| 解读/法务「风险点」用户混淆 | Skills 文档明确视角差异；字段名区分 `bid_risk_items` vs `legal risk_items` |

---

## 附录 A：工作区 manifest 扩展

分析完成后 `manifest.json` 新增 stages：

```json
{
  "stages": {
    "interpret": { "status": "success" },
    "template": { "status": "success" },
    "legal": { "status": "success" }
  },
  "outputs": {
    "interpretation": "interpretation.json",
    "templates": "templates/index.json",
    "legal_review": "legal_review.json"
  }
}
```
