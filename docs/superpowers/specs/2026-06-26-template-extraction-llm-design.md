# 设计规格：LLM 驱动模版提取（Plan → Extract → Merge）

**版本**: 1.0  
**日期**: 2026-06-26  
**状态**: 已批准（brainstorming）  
**依赖**: `doc_chunk` 包、`tender_insights` 包、现有 `viewer/` 解读页  
**实现方案**: 方案 1 — Plan → Extract → Merge 三阶段 Pipeline

---

## 1. 概述

### 1.1 背景

当前模版提取（`tender_insights/template/extractor.py`）完全依赖 `outline.json` 节点标题关键词（`附件`、`承诺书`、`授权`、`声明`、`委托`），规则分类、不调用 LLM。当 outline 粒度较粗（仅一级章节）时，即使 `content.md` 内含完整模版正文（如「第四章参选文件格式」下的授权书、声明函），`templates/index.json` 也会为空。

典型失败案例：鼎信工作餐服务项目 — outline 仅 6 个一级节点，`manifest.json` 中 `stages.template.status = success`，但 `templates: []`。

### 1.2 已确认决策

| 维度 | 决策 |
|------|------|
| LLM 职责 | **只识别边界**；正文由系统 `slice_for_llm` 机械切片，保留标题层级、表格、图片引用 |
| 发布范围 | **独立「提取模版」按钮** + **「开始解读」末尾**均调用同一套新 pipeline |
| 上下文输入 | 仅 `content.md` + `outline.json`（+ `content.blocks.json` 用于表格）；**不读** `interpretation.json` |
| 分片回退 | outline 子节点 → Markdown heading（`#`~`####`）→ 固定字符块（带 overlap） |
| 实现路径 | Plan → Extract → Merge 三阶段（仿 `gen_catalog` 分步 + 进度模式） |

### 1.3 核心用户流程

1. 解读页 `/interpret` 选择会话或上传文件
2. 点击「**提取模版**」→ 后台：分片计划 → 逐片 LLM 识别 → 机械切片 → 合并 → 写 `templates/`
3. 或点击「**开始解读**」→ doc_chunk → interpret → **新模版 pipeline**（替换旧规则逻辑）
4. 进度条显示 `template_plan` / `template_extract (2/5)` / `template_merge`
5. LLM Tab 展示 `template_plan`、`template_extract` 调用记录
6. 模版 Tab 展示提取结果，可查看原文

### 1.4 范围边界

**In Scope (v1)**

- 重写 `extract_templates_workspace` 为 LLM 三阶段 pipeline
- `run_interpret_job` 末尾调用新 pipeline（`include_template=True` 时）
- Viewer 新增 `job_kind=template`、按钮、进度阶段、LLM 日志
- 产物：`templates/plan.json`、`templates/index.json`、`templates/*.md`
- 配置项：`TEMPLATE_*` 环境变量
- 单元/集成测试（含鼎信类粗 outline fixture）

**Out of Scope (v1)**

- 读取 `interpretation.json` 作为辅助上下文
- LLM 改写模版正文
- 跨会话模版对比、在线编辑、导出
- 模版提取的 step-by-step 暂停/恢复（session 持久化仅写 plan 供 debug，不做断点续跑 UI）
- 合并阶段的 LLM 校验（纯规则去重）

---

## 2. 架构

### 2.1 模块结构

```
src/tender_insights/template/
├── planner.py          # 确定性分片 + 可选 LLM plan 校验
├── sharder.py          # 三层回退：outline 子节点 → heading → char
├── prompts.py          # template_plan / template_extract system & user
├── models.py           # Plan、Shard、LLM response、index schema 1.1
├── extractor.py        # 编排入口（替换现有规则逻辑）
├── merger.py           # 跨片去重合并
├── slicer.py           # char 边界 → slice_for_llm → 写 .md
├── session.py          # templates/session.json（进度元数据，可选）
├── detector.py         # 保留供测试/回退，生产路径不再调用
└── classifier.py       # 保留；type 以 LLM 输出为准，规则作 fallback
```

**API 层**（`tender_insights/api.py`）：

```python
def run_template_job(
    workspace: OutputWorkspace,
    *,
    client: LLMClient | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    setup_logging: bool = True,
) -> TemplatesIndexFile: ...

def extract_templates(...)  # 委托 run_template_job 或共享核心
```

`run_interpret_job` 在 `include_template=True` 时改调 `run_template_job`（或共享的 `extract_templates_workspace` 新实现）。

### 2.2 数据流

```
content.md + outline.json + content.blocks.json
        │
        ▼
   [sharder] 确定性分片 → templates/plan.json
        │
        ▼
   [LLM template_plan] 校验/补充计划（1 次调用）
        │
        ▼
   对每个 shard:
     slice_for_llm(shard) → [LLM template_extract] → TemplateHit[]
        │
        ▼
   [slicer] 每个 hit → templates/{type}-{seq}.md
        │
        ▼
   [merger] 跨片去重 → templates/index.json
        │
        ▼
   manifest.json stages.template 更新
```

### 2.3 Viewer 集成

```
viewer/viewer/
├── routes/interpret.py       # POST .../template, upload?job_kind=template
├── services/interpret_pipeline.py  # run_template_on_workspace / run_template_job
├── models.py                 # job_kind 增加 "template"
├── services/interpret_job_registry.py
└── static/interpret.html/js  # 按钮、STAGES、轮询 LLM
```

---

## 3. 分片计划（Plan）

### 3.1 确定性分片（sharder）

输入：`content.md` 全文经 `slice_for_llm` 后的字符长度（或 token 估算）。

阈值（可配置）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `TEMPLATE_WHOLE_DOC_MAX_CHARS` | 80000 | 低于此值整篇一片 |
| `TEMPLATE_SHARD_MAX_CHARS` | 24000 | 单片上限 |
| `TEMPLATE_CHAR_CHUNK_OVERLAP` | 500 | 字符块切分重叠 |

算法：

1. 若 `len(content) ≤ TEMPLATE_WHOLE_DOC_MAX_CHARS` → 1 片 `strategy=whole_doc`
2. 否则按 `outline` **level=1** 节点切分（`node_char_range`）
3. 对任一片若 `len > TEMPLATE_SHARD_MAX_CHARS`：
   - 有 **outline 子节点** → 按子节点再拆（`strategy=outline_child`）
   - 无子节点 → 扫描片内 **Markdown heading**（`#` ~ `####`）拆（`strategy=heading`）
   - 仍超大 → **字符块**切分（`strategy=char`，带 overlap）
4. 每片记录：`shard_id`、`section_path`、`char_start`、`char_end`、`strategy`、`char_count`

输出写入 `templates/plan.json`：

```json
{
  "schema_version": "1.0",
  "planned_at": "2026-06-26T12:00:00+00:00",
  "whole_doc_chars": 45000,
  "shard_count": 3,
  "shards": [
    {
      "shard_id": "shard-001",
      "strategy": "outline_l1",
      "section_path": ["第四章参选文件格式"],
      "char_start": 12000,
      "char_end": 28000,
      "char_count": 16000
    }
  ],
  "merge_policy": "dedupe_by_char_overlap_and_title"
}
```

### 3.2 LLM Plan 调用

- `call_type`: `template_plan`
- `segment_id`: `plan`
- 输入：outline 一级标题列表、各 shard 摘要（`section_path` + `char_count`）、招标文档标题（来自 `manifest.source.title`）
- 输出（JSON）：`shard_count` 确认、`priority_sections`（建议重点扫描章节）、`notes`（如「第四章为格式章，预计含 5+ 模版」）
- LLM **不修改** shard 边界（v1）；仅补充元数据写入 `plan.json` 的 `llm_notes` 字段
- 可通过 `TEMPLATE_PLAN_ENABLED=false` 跳过 LLM plan，仅保留确定性分片

---

## 4. 提取阶段（Extract）

### 4.1 每片 LLM 调用

- `call_type`: `template_extract`
- `segment_id`: `shard-001` 等
- User prompt 包含：
  - 当前 shard 的 `slice_for_llm` 正文（表格已替换为 `llm_text`）
  - `char_start` 偏移说明：返回的 `char_start`/`char_end` 必须为 **相对 content.md 的全局坐标**
  - 任务定义：识别发标单位要求投标人**填写、签字、盖章、按格式提交**的范本/表格/函件
  - 排除：纯采购需求描述、合同条款正文、评审办法说明（无填写栏位）
  - 输出 schema 见 4.2

### 4.2 LLM 响应 Schema（`TemplateExtractResponse`）

```json
{
  "templates": [
    {
      "title": "法定代表人（单位负责人）授权书",
      "type": "authorization",
      "type_label": "授权书",
      "char_start": 15200,
      "char_end": 16800,
      "confidence": 0.95,
      "source_excerpt": "本授权书声明：本人…"
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `type` | `commitment` / `authorization` / `declaration` / `other` |
| `type_label` | 中文标签，LLM 生成 |
| `char_start` / `char_end` | `content.md` 全局字符锚点 |
| `confidence` | 0–1 |
| `source_excerpt` | 模版开头 50–200 字，用于去重与 Viewer 展示 |

片内无模版：`templates: []`。

### 4.3 机械切片（slicer）

对每个 hit：

1. 校验 `char_start`/`char_end` 在 `[0, len(content_md))` 且 `start < end`
2. `md = slice_for_llm(workspace, content_md, start, end)` — 保留 heading、表格 sidecar、图片 `![]()` 引用
3. 写入 `templates/{type}-{seq:03d}.md`（`seq` 按 type 递增，合并后重编号）
4. 构建 `TemplateEntry`（见 5.1）

---

## 5. 合并阶段（Merge）

### 5.1 去重规则（确定性）

对所有 shard 的 hits 合并：

1. **坐标重叠**：两 hit 的 `[start, end)` 交集 / 较短区间长度 > 0.5 → 保留 `confidence` 较高者
2. **标题归一化**：去空格、全半角、括号后相同，且 `source_excerpt` Jaccard > 0.8 → 合并为一条
3. 按 `char_start` 排序，重新分配 `id`（`tpl-001`…）、文件名

### 5.2 输出 Schema（`TemplatesIndexFile` v1.1）

在 v1.0 基础上扩展（向后兼容）：

| 新增字段 | 位置 | 说明 |
|----------|------|------|
| `extraction_method` | `TemplateEntry` | 固定 `"llm"` |
| `shard_id` | `TemplateEntry` | 来源分片，可选 |
| `plan_ref` | 顶层 | `"templates/plan.json"` |
| `shard_count` | 顶层 | 分片总数 |

`schema_version` 升为 `"1.1"`；旧消费者读 `templates[]` 仍可用。

### 5.3 空结果

`templates: []` 时仍写 `index.json` 与 `plan.json`，`manifest.stages.template.status = success`，`warnings` 可追加 `"no templates identified"`。

---

## 6. LLM 日志与进度

### 6.1 日志

复用 `tender_insights/interpret/llm_logging.py`：

- `setup_interpret_llm_logging(workspace)` → `llm_calls.jsonl`
- `call_type`: `template_plan`、`template_extract`
- `segment_id`: `plan` / `shard-001` / …
- `log_llm_attempt` 记录重试与 validation 错误

### 6.2 进度回调（`on_progress`）

| stage | message 示例 | payload |
|-------|-------------|---------|
| `template_plan` | 制定模版提取计划… | `shard_count`, `current=0`, `total=shard_count+2` |
| `template_extract` | 提取模版 (2/5) | `shard_id`, `current`, `total`, `detail=section_path` |
| `template_merge` | 合并模版结果… | — |
| `done` | 模版提取完成 | `template_count` |

Viewer `step_total = 1 (plan) + shard_count + 1 (merge)`。

---

## 7. Viewer API

### 7.1 新增端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/interpret/sessions/{id}/template` | 对已就绪工作区跑模版 job |
| `POST` | `/api/interpret/upload?job_kind=template` | 上传 + pipeline（若需要）+ 模版 |

### 7.2 job_kind

`InterpretJobRecord.job_kind` 扩展为：`interpret` | `brief` | `gen_catalog` | **`template`**

### 7.3 前置条件

- 工作区含 `content.md`、`outline.json`（`validate_workspace` 通过）
- **不要求** `interpretation.json`
- 若工作区未就绪：先 `prepare_workspaces`（与 brief 相同模式）

### 7.4 前端

- `interpret.html`：新增按钮「提取模版」
- `interpret.js`：`TEMPLATE_STAGES = [..., "template_plan", "template_extract", "template_merge"]`
- 轮询时 `job.stage` 含 `template_*` 时刷新 LLM Tab
- 完成后刷新模版 Tab（`loadSessionData`）

---

## 8. 配置

`.env.example` 新增：

```bash
# Template extraction
TEMPLATE_WHOLE_DOC_MAX_CHARS=80000
TEMPLATE_SHARD_MAX_CHARS=24000
TEMPLATE_CHAR_CHUNK_OVERLAP=500
TEMPLATE_PLAN_ENABLED=true
```

`InsightsConfig` 增加对应字段，`from_env()` 读取。

---

## 9. 错误处理

| 场景 | 行为 |
|------|------|
| LLM JSON 解析失败 | `extract_json_model` 重试（`max_retries`） |
| 单片提取失败 | 记录 warning，继续下一片；最终合并可用片结果 |
| 全部片失败 | job `status=failed`，session `error` 写入原因 |
| char 边界越界 | 丢弃该 hit，log warning |
| 工作区无 outline | 仅 whole_doc 或 char 分片（outline 为空时退化为 char） |

---

## 10. 测试计划

### 10.1 单元测试

- `sharder`：whole_doc / outline_l1 / heading / char 四层路径
- `merger`：重叠去重、标题去重
- `slicer`：边界校验、`slice_for_llm` 集成（mock workspace）

### 10.2 集成测试

- FakeLLM 返回固定 `TemplateExtractResponse`，端到端写 `templates/`
- 鼎信类 fixture：6 节点 outline + 第四章含授权书/声明函 → `templates` 非空

### 10.3 Viewer 测试

- `POST /sessions/{id}/template` 返回 job_id
- 进度含 `template_extract`
- `llm_calls.jsonl` 含 `template_plan`、`template_extract`
- `test_interpret_pipeline` 更新：新 pipeline 产出非空或 FakeLLM 可控

### 10.4 契约

- `TemplatesIndexFile` schema 1.1 校验
- v1.0 仅 `templates: []` 的 fixture 仍通过

---

## 11. 迁移与兼容

- CLI `tender-insights template` 自动使用新 pipeline，无需新子命令
- 旧工作区重跑模版会覆盖 `templates/`（`overwrite` 语义与 interpret 一致）
- `detector.py` / `classifier.py` 不删除，避免破坏 import；主路径不再调用

---

## 12. 实现顺序建议

1. `sharder` + `planner` + `plan.json` 模型
2. `prompts` + `TemplateExtractResponse` + 单片 extract
3. `slicer` + `merger` + `extractor` 编排
4. `api.run_template_job` + `run_interpret_job` 切换
5. Viewer 按钮、job_kind、进度、LLM Tab
6. 测试与 `.env.example`

---

## 附录：Prompt 要点摘要

**System（template_extract）**：

- 你是招标文件模版提取专家
- 只输出 JSON，标注模版在原文中的字符范围
- 模版 = 投标人须按发标方格式填写/签署/盖章提交的文件范本
- 不要提取：纯说明性章节、合同正文、评分办法（无填写格式）
- 常见位置：参选/投标文件格式章、附件、承诺书、授权书、声明函、报价表格式

**User**：shard 正文 + 全局坐标偏移 + 输出 schema 示例
