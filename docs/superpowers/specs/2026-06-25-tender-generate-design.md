# 设计规格：tender-generate 投标目录生成

**版本**: 1.0  
**日期**: 2026-06-25  
**状态**: 待审阅  
**Feature ID**: `007-tender-generate`  
**前置**: `006-interpret-v2`（`interpretation.json` + `directory_outline`）

---

## 1. 概述

新增 `tender-generate` 阶段（CLI：`tender-insights gen-catalog`），在招标文件**已解读**的前提下，生成**投标响应目录方案**（非章节正文）。

目录方案须：

1. 严格对齐 `directory_requirements`、响应须知与应标要求
2. 显式关联**废标项**、**评分项**，便于评标时对应得分点
3. 每个节点含**章节概要**（`summary`）与**撰写规范**（`writing_spec`）
4. 工作区存在模板时，将 `templates/` 挂载到对应节点
5. LLM 请求携带 `interpretation.overview` 与 `tender_brief` 概要信息
6. 不变提示词内容前置，利于 provider prompt cache

**硬约束**：不修改 `doc_chunk` 代码；所有新逻辑在 `tender_insights` 与 `viewer` 内。

**范围外**：各章节正文撰写、Word 导出、目录手工编辑（本期仅预览 + accept 落盘）。

---

## 2. 已确认决策

| 决策点 | 选择 |
|--------|------|
| 产物范围 | **A** — 仅投标目录方案（树 + 概要 + 撰写规范 + 引用），不生成正文 |
| 前置依赖 | **C** — `interpretation.json` 必须；`templates/index.json`、`tender_brief.json` 尽量齐全，缺失时降级并提示 |
| 遍历策略 | **节点级完善** — 每步 LLM 输入/输出均为**完整目录树**，不做分段合并 |
| 运行模式 | **按步**（`step`）或 **一次性**（`auto`，默认） |
| 落盘交互 | **预览 + accept** — `bid_outline.draft.json` → 用户确认 → `bid_outline.json` |
| Viewer 关联 | **A** — 绑定解读会话；`/interpret` 加「生成目录」；新页 `/gen-catalog?session_id=...` |
| 进度 | 必须展示步骤进度（当前节点、已完成/总数、百分比） |
| LLM 日志 | 所有请求追加写入工作区 `llm_calls.jsonl` |
| 包边界 | 只改 `tender_insights`、`viewer`；`doc_chunk` 只读 |

---

## 3. 产物与数据模型

### 3.1 工作区文件

| 路径 | 说明 |
|------|------|
| `bid_outline.draft.json` | 当前工作副本；每步 LLM 完成后更新 |
| `bid_outline.json` | 用户 accept 后的正式产物 |
| `bid_outline.md` | accept 时一并写入的人类可读导出 |
| `gen_catalog/session.json` | 按步/一次性运行的状态机 |
| `llm_calls.jsonl` | 与 interpret 共用，追加 `gen_catalog_*` 记录 |
| `manifest.json` | 新增 `stages.gen_catalog` |

### 3.2 `BidOutlineFile`（schema 1.0）

```text
BidOutlineFile:
  schema_version: "1.0"
  source_workspace: str
  generated_at: ISO8601
  accepted_at: ISO8601 | null
  interpretation_schema: str          # 来源 interpretation.json 的 schema_version
  mode: "step" | "auto"
  status: "running" | "paused" | "awaiting_accept" | "accepted"
  step_index: int
  step_total: int
  overview_snapshot: object          # interpretation.overview 快照（便于离线查看）
  brief_snapshot: object | null       # tender_brief 核心字段快照
  root: BidOutlineNode

BidOutlineNode:
  id: str
  title: str
  level: int
  order: int
  mandatory: bool
  number: str | null
  summary: str                       # 本章概要（给写标人）
  writing_spec: str                   # 撰写规范（格式、页数、签章、响应要点）
  template_ref: TemplateRef | null
  scoring_refs: list[str]             # scoring_items.id
  disqualification_refs: list[str]    # disqualification_items.id
  bid_risk_refs: list[str]            # bid_risk_items.id（可选提醒）
  source_refs: list[SourceRef]         # 招标文件出处
  children: list[BidOutlineNode]

TemplateRef:
  template_id: str                     # templates/index.json entry id
  file: str
  type: str

SourceRef:
  section_path: list[str]
  char_start: int | null
  char_end: int | null
  excerpt: str | null
```

### 3.3 `gen_catalog/session.json`

```json
{
  "mode": "step",
  "status": "paused",
  "step_index": 2,
  "step_total": 15,
  "current_node_id": "bid-003",
  "current_node_title": "技术方案",
  "node_queue": ["bid-001", "bid-002", "bid-003"],
  "completed_steps": ["initial", "bid-001", "bid-002"],
  "job_id": "uuid",
  "updated_at": "2026-06-25T12:00:00+00:00"
}
```

---

## 4. 架构与流水线

### 4.1 模块布局

| 路径 | 职责 |
|------|------|
| `tender_insights/gen_catalog/models.py` | Pydantic 模型 |
| `tender_insights/gen_catalog/prompts.py` | `GEN_CATALOG_INITIAL_SYSTEM`、`GEN_CATALOG_REFINE_SYSTEM`（固定前置） |
| `tender_insights/gen_catalog/context.py` | 组装解读/brief/模板/废标/评分上下文 |
| `tender_insights/gen_catalog/excerpt.py` | 按节点从 `interpret/source_content.md` 选取摘录（≤2000 字；<200 字与后续段落拼接） |
| `tender_insights/gen_catalog/extractor.py` | 主流程：`run_gen_catalog()` |
| `tender_insights/gen_catalog/session.py` | 读/写 `gen_catalog/session.json`，步进逻辑 |
| `tender_insights/gen_catalog/accept.py` | draft → `bid_outline.json` + `bid_outline.md` |
| `tender_insights/gen_catalog/render.py` | draft/outline → Markdown |
| `tender_insights/api.py` | 暴露 `run_gen_catalog_job()`、`continue_gen_catalog()`、`accept_gen_catalog()` |
| `tender_insights/cli/main.py` | `gen-catalog` 子命令 |
| `viewer/viewer/routes/gen_catalog.py` | REST API |
| `viewer/viewer/services/gen_catalog_pipeline.py` | 后台任务 + 进度 |
| `viewer/viewer/static/gen-catalog.html` + `gen-catalog.js` | 测试页 UI |

### 4.2 流水线

```text
validate_prerequisites(workspace)
    ↓
load interpretation.json + tender_brief.json? + templates/index.json?
    ↓
Step 0: gen_catalog_initial (LLM)
    → 输入：固定 GEN_CATALOG_INITIAL_SYSTEM + 解读概要 + brief + directory_requirements
           + 废标/评分摘要 + 模板清单
    → 输出：完整 BidOutline → 写入 bid_outline.draft.json
    → [mode=step] 暂停
    ↓
Step 1…N: for each node in preorder(node_queue):
    gen_catalog_node_plan (LLM) → {needs_optimization, refinement_plan}
    if needs_optimization:
        gen_catalog_node_apply (LLM) → 完整 BidOutline（替换整棵树）→ 更新 draft
    → [mode=step] 暂停
    ↓
status = awaiting_accept
    ↓
用户 accept → bid_outline.json + bid_outline.md
```

> **2026-06-26 更新：** 节点完善步已升级为 Plan → 条件 Apply 两步流程，详见 `docs/superpowers/specs/2026-06-26-gen-catalog-node-refine-design.md`。

**关键约束**：Step 0 与 Apply 步的 LLM 响应为**整棵目录树替换**；Plan 步仅输出评估 JSON，不返回 outline。

### 4.3 节点队列

对 `bid_outline.draft.json` 的 `root` 做**前序遍历**（父节点先于子节点），扁平化为 `node_queue`。  
初始 Step 0 完成后根据树结构计算 `step_total = 1 + len(node_queue)`（1 为 initial 步）。

若某步 LLM 调整了树结构（增删节点），**下一步**起按新树重新计算剩余队列；已在 `completed_steps` 中的节点不再重复处理。

### 4.4 前置校验

| 检查 | 失败行为 |
|------|----------|
| `interpretation.json` 存在 | 拒绝启动（HTTP 400 / CLI exit 1） |
| `directory_requirements` 或 `directory_outline.nodes` 非空 | 拒绝启动 |
| `tender_brief.json` 缺失 | 警告继续；user prompt 省略 brief 块 |
| `templates/index.json` 缺失 | 警告继续；所有 `template_ref` 为 null |
| 已有 `bid_outline.json` 且未 `--overwrite` | 拒绝启动 |

---

## 5. 双提示词与缓存

### 5.1 提示词分离

| 阶段 | call_type | System（固定，最前） | User（动态） |
|------|-----------|---------------------|--------------|
| 初始生成 | `gen_catalog_initial` | `GEN_CATALOG_INITIAL_SYSTEM`：角色、输出 JSON schema、废标/评分对齐规则、撰写规范要求 | 解读 overview、brief、tender_brief 五字段、directory_requirements 树、废标/评分明细摘要、模板清单 |
| 节点完善 | `gen_catalog_node_plan` / `gen_catalog_node_apply` | `GEN_CATALOG_NODE_SYSTEM`（Plan/Apply 共用） | Plan：招标概要 + 目录树 + 摘录；Apply：同上 + 优化方案 |

### 5.2 缓存策略

1. **System message** 完全固定（含 schema 与规则），不嵌入 workspace 路径
2. **User message** 内将不变块（如废标/评分 id 表）排在动态树之前
3. 同一 workspace 连续按步请求时，system 内容字节级一致

### 5.3 LLM 响应格式

```json
{
  "outline": { "id": "bid-root", "title": "...", "children": [...] },
  "changes_summary": "本步对目录的主要调整说明"
}
```

校验失败重试 ≤ `config.max_retries`（默认 2），与 interpret 一致。

### 5.4 LLM 日志

复用 `tender_insights.interpret.llm_logging`（或抽到 `tender_insights.common.llm_logging`）：

- 启动 gen-catalog 前设置 `INTERPRET_LOG_JSONL={workspace}/llm_calls.jsonl`
- 每次调用记录 `call_type`、`segment_id`（节点 id 或 `initial`）、`messages`、`response`、`attempt`

---

## 6. 运行模式

### 6.1 一次性（`mode=auto`，默认）

CLI / API 连续执行 Step 0 → 所有 Step N；`on_progress` 实时更新；结束后 `status=awaiting_accept`。

### 6.2 按步（`mode=step`）

| 动作 | 行为 |
|------|------|
| 首次「生成目录」 | 仅 Step 0；写 draft + session；`status=paused` |
| 「继续」 | 执行队列中下一节点；更新 draft；`status=paused` |
| 全部完成 | `status=awaiting_accept` |
| 「确认落盘」 | 调用 accept；写 `bid_outline.json` |

支持「从头重来」：`--restart` 清除 draft 与 session，重新 Step 0。

### 6.3 进度回调

```python
on_progress("gen_catalog", {
    "message": "正在完善节点：技术方案",
    "detail": "节点 3 / 14",
    "current": 3,
    "total": 14,
    "step": "gen_catalog_node",       # gen_catalog_initial | gen_catalog_node | awaiting_accept
    "node_id": "bid-003",
    "node_title": "技术方案",
})
```

---

## 7. CLI

```bash
# 一次性生成（默认）
tender-insights gen-catalog ./output/my-bid

# 按步：仅初始目录
tender-insights gen-catalog ./output/my-bid --step --once

# 按步：继续下一节点
tender-insights gen-catalog ./output/my-bid --continue

# 确认落盘
tender-insights gen-catalog ./output/my-bid --accept

# 从头重来
tender-insights gen-catalog ./output/my-bid --restart --step --once
```

| 参数 | 说明 |
|------|------|
| `--step` | 按步模式（与 `--once` / `--continue` 配合） |
| `--once` | 只执行下一步后暂停 |
| `--continue` | 从 session 暂停处执行下一步 |
| `--accept` | draft → 正式产物 |
| `--restart` | 清除 gen_catalog 状态重新开始 |
| `--overwrite` | 覆盖已有 `bid_outline.json` |

---

## 8. Viewer 测试页

### 8.1 路由与导航

- 新页：`GET /gen-catalog?session_id={id}`
- `interpret.html` 导航栏增加「目录生成」Tab；解读成功会话显示「生成目录」按钮，跳转携带 `session_id`
- 前置：会话工作区已有 `interpretation.json`

### 8.2 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/gen-catalog/sessions/{session_id}/start` | `?mode=auto\|step` 启动 |
| `POST` | `/gen-catalog/sessions/{session_id}/continue` | 按步继续 |
| `POST` | `/gen-catalog/sessions/{session_id}/accept` | 确认落盘 |
| `GET` | `/gen-catalog/jobs/{job_id}` | 进度轮询 |
| `GET` | `/gen-catalog/sessions/{session_id}/draft` | 当前 draft 树 |
| `GET` | `/gen-catalog/sessions/{session_id}/llm-calls` | 复用 llm_calls 读取逻辑 |

### 8.3 UI 要素

1. **模式选择**：一次性 / 按步（默认按步，便于调试）
2. **进度面板**：总进度条、当前步骤名、节点标题、`current/total`
3. **目录树预览**：可展开树；选中节点显示 summary、writing_spec、模板与评分/废标引用
4. **操作按钮**：生成 / 继续 / 确认落盘 / 从头重来
5. **LLM 调用**：可折叠列表，展示 `call_type`、节点、时间（数据来自 `llm_calls.jsonl`）
6. **前置缺失提示**：无 brief / 无模板时顶部黄色提示

### 8.4 Job 模型

扩展 `InterpretJobState`（`job_kind="gen_catalog"`），字段与 interpret job 对齐：`progress_percent`、`step_current`、`step_total`、`message`、`detail`。

---

## 9. 错误处理

| 场景 | 行为 |
|------|------|
| LLM JSON 校验失败 | 重试；耗尽后 job `failed`，保留上次有效 draft |
| 按步 continue 但无 session | HTTP 400「无进行中的生成任务」 |
| accept 但 status ≠ awaiting_accept | HTTP 400 |
| 解读会话无 interpretation.json | HTTP 400，引导先解读 |
| 节点队列中 id 在树中不存在 | 跳过并记 warning 日志 |
| 并发生成同一 session | 拒绝第二个 job（409） |

失败时 `gen_catalog/session.json` 保留 `status=failed` + `error`，允许 `--restart`。

---

## 10. 测试计划

### 10.1 单元测试（`tests/tender_insights/unit/test_gen_catalog.py`）

- 前置校验：缺 interpretation 拒绝；缺 brief 降级警告
- 节点队列前序遍历与步进 session 状态机
- excerpt 选取：2000 上限、<200 拼接
- accept 写入 `bid_outline.json` / `bid_outline.md`
- FakeLLM：initial + 2 节点 refine 后树字段完整

### 10.2 契约测试（`tests/tender_insights/contract/test_bid_outline_schema.py`）

- `bid_outline.json` 符合 schema 1.0
- `scoring_refs` / `disqualification_refs` 引用存在于 interpretation

### 10.3 Viewer 测试

- `viewer/tests/api/test_gen_catalog_api.py`：start / continue / accept / draft
- `viewer/tests/unit/test_gen_catalog_pipeline.py`：进度回调字段
- 静态资源：`gen-catalog.html` 含进度条与继续按钮

### 10.4 测试夹具

- 复用已有 interpret 工作区 fixture + `FakeLLMClient` 返回固定目录树

---

## 11. 不在本期范围

- 章节正文生成
- 页面上手工编辑节点后保存
- Word / docx 导出
- 自动串联进 `tender-insights all`（可后续加 `--with-gen-catalog`）
- 新建独立 Cursor skill 文件（实现完成后补 `tender-gen-catalog/SKILL.md`）

---

## 12. 实现顺序建议

1. `tender_insights/gen_catalog/*` 模型 + 初始生成 + 单节点 refine + session
2. CLI `gen-catalog` 子命令 + 契约测试
3. `accept` + `render` + Markdown 导出
4. Viewer API + pipeline + 进度
5. `gen-catalog.html` / `gen-catalog.js` + interpret 页入口
6. README 与 skill 文档更新
