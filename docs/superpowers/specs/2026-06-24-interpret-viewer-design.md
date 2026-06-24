# 设计规格：招标解读 Viewer 页面

**版本**: 1.0  
**日期**: 2026-06-24  
**状态**: 已批准（brainstorming）  
**依赖**: `doc_chunk` 包、`tender_insights` 包、现有 `viewer/` 应用  
**实现方案**: 方案 A — 扩展 viewer，新增合并服务与解读任务链

---

## 1. 概述

### 1.1 背景

`viewer/` 已提供 doc_chunk 切片预览（上传 → outline 树 + 章节 Markdown）。`tender_insights` 已实现招标解读（废标项、得分项、投标风险、目录要求）与模版提取，但目前仅 CLI/API 可用，无 Web 调试入口。

本设计在现有 `viewer/` 应用内新增独立 **招标解读** 页面，支持上传 1～2 份同一招标项目的招标文件（商务+技术分册，或主文件+补充/澄清文件），合并到单一工作区后运行解读与模版提取，并以分类 Tab 展示结构化结果。

### 1.2 已确认需求

| 维度 | 决策 |
|------|------|
| 文件场景 | 同一招标项目的两个分册（商务+技术）或主文件+补充/澄清文件 |
| 文件数量 | 1～2 个，合并到**一个工作区** |
| 合并顺序 | 按**上传顺序**拼接（先传的在前） |
| 分析范围 | **解读**（`interpretation.json`）+ **模版提取**（`templates/`） |
| 结果展示 | 分类 Tab + 卡片（摘要/摘录），可跳转对应章节原文 |
| 页面形态 | 独立 `/interpret` 页面，顶栏导航在「切片预览」与「招标解读」间切换 |
| 定位 | 内部开发调试工具，本机单用户，无鉴权 |

### 1.3 核心用户流程

1. 打开 `http://127.0.0.1:8765/interpret`
2. 选择文件 1（必填），可选文件 2（补充文件）
3. 点击「开始解读」→ 后台依次：doc_chunk pipeline →（可选）工作区合并 → interpret → template
4. 进度条显示当前阶段
5. 完成后在 Tab 中浏览废标项、得分项、风险、目录要求、模版
6. 点击卡片「查看原文」在侧栏渲染章节 Markdown；或「在切片预览中打开」跳转到 `/` 并定位节点

### 1.4 范围边界

**In Scope (v1)**

- 上传 1～2 个 `.docx` / `.pdf`，按上传顺序合并工作区
- 合并后运行 `interpret_document` + `extract_templates`
- 解读结果五类 Tab 展示
- 解读会话历史（本机 JSON，最近 20 条）
- 原文跳转（侧栏 panel + 切片预览深链接）
- 切片预览页顶栏导航与 URL 参数（`?session=&node=`）

**Out of Scope (v1)**

- 法务审核（`legal_review`）
- 打开已有工作区直接解读（仅上传触发）
- 三文件及以上合并
- 解读结果在线编辑或导出
- 远程部署 / 多用户鉴权

---

## 2. 架构

### 2.1 方案选择

采用**方案 A：扩展 viewer**，在 `viewer/` 内新增合并服务与解读任务链，直接调用 `tender_insights` Python API。`tender_insights` 与 `doc_chunk` 核心逻辑不改动。

```
tender_skills/
├── src/tender_insights/     # 不变，通过 API 调用
├── viewer/
│   ├── viewer/
│   │   ├── main.py          # 注册 /interpret 路由与 interpret API
│   │   ├── routes/
│   │   │   └── interpret.py # 解读上传、job、result API
│   │   ├── services/
│   │   │   ├── workspace_merge.py    # 双工作区合并
│   │   │   └── interpret_pipeline.py # pipeline → merge → interpret → template
│   │   └── static/
│   │       ├── interpret.html
│   │       ├── interpret.js
│   │       └── style.css    # 共用，追加解读页样式
│   └── pyproject.toml       # 增加 tender-insights 依赖
```

### 2.2 页面结构

```text
┌─────────────────────────────────────────────────────────┐
│  顶栏导航： [切片预览]  [招标解读 ●]                    │
├─────────────────────────────────────────────────────────┤
│  /interpret 页面                                         │
│  ┌─ 上传区 ─────────────────────────────────────────┐  │
│  │  文件 1（必填）  [选择文件]                          │  │
│  │  文件 2（可选）  [选择文件]  标签：补充文件（可选）    │  │
│  │  [开始解读]                                         │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌─ 进度条 ─ extract → merge → interpret → template ─┐  │
│  ┌─ 结果区（完成后显示）──────────────────────────────┐  │
│  │  Tab: 废标项 | 得分项 | 风险 | 目录 | 模版          │  │
│  │  卡片列表 → 查看原文 / 在切片预览中打开              │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.3 会话与存储

| 路径 | 说明 |
|------|------|
| `~/.doc-chunk-viewer/interpret_sessions.json` | 解读会话索引（最近 20 条） |
| `~/.doc-chunk-viewer/uploads/interpret/<session_id>/` | 原始上传文件 |
| `~/.doc-chunk-viewer/workspaces/<session_id>/` | 合并后的最终工作区 |

解读会话与切片会话分开存储，避免污染现有 `sessions.json`。

---

## 3. 工作区合并规则

两个文件各自完整跑 doc_chunk pipeline（`skip_refine=True`, `skip_enrich=True`），产出临时工作区 `ws1`、`ws2`，再按上传顺序合并到目标工作区 `ws_merged`。

### 3.1 `content.md` 拼接

```text
ws_merged/content.md =
  ws1/content.md
  + "\n\n"
  + "<!-- source: {file2_name} -->\n"
  + ws2/content.md
```

`offset2 = len(ws1.content) + len(separator)`，file2 所有字符锚点统一加上 `offset2`。

### 3.2 `outline.json` 合并

| 规则 | 说明 |
|------|------|
| file1 节点 | 原样保留（`node_id`、锚点、父子关系不变） |
| file2 节点 | `node_id` 加前缀 `m2:`（如 `n-003` → `m2:n-003`），`parent_id` 同步改写 |
| 锚点偏移 | file2 所有 `anchor.char_start/char_end/block_start/block_end` += `offset2` |
| `sort_order` | file1 保持原值；file2 各节点 `sort_order += max_sort_order(ws1)` |
| 顶层节点 | 不插入合成根节点；file2 的 level-1 节点直接接在 file1 树之后 |
| `strategy` | 取 file1 的 strategy；`derived_from` 记为 `merged:{file1_name}+{file2_name}` |

### 3.3 其他产物

| 文件 | 处理 |
|------|------|
| `images/` | 复制 file1 原样；file2 图片若重名则加 `m2_` 前缀，并同步更新 file2 在 `content.md` 内的引用路径 |
| `content_blocks.json` | 若存在则合并：file2 的 `char_start/char_end` 偏移，block 索引顺延 |
| `document_tree.json` / `chunks/` | v1 不合并（解读和模版提取不依赖） |
| `manifest.json` | 合并后重写，记录 `sources: [file1, file2]` 和 `merged_at` |

### 3.4 单文件退化

只上传 1 个文件时跳过 merge 步骤，直接把 pipeline 工作区作为最终工作区。

### 3.5 合并后校验

- 所有 `char_start < char_end <= len(content.md)`
- `node_id` 无重复
- `parent_id` 引用有效

校验失败则 job 标记 `failed`。

---

## 4. 任务流水线与 API

### 4.1 任务阶段

| 阶段 | 内部 stage | 前端展示文案 | 说明 |
|------|-----------|-------------|------|
| 1 | `pipeline_1` | 正在提取文件 1… | doc_chunk pipeline |
| 2 | `pipeline_2` | 正在提取文件 2… | 仅有第二个文件时执行 |
| 3 | `merge` | 正在合并工作区… | 仅双文件时执行 |
| 4 | `interpret` | 正在解读招标… | `interpret_document(ws)` |
| 5 | `template` | 正在提取模版… | `extract_templates(ws)` |
| 6 | `done` | 完成 | — |

任务在 `BackgroundTasks` + `asyncio.to_thread` 中执行，前端 1s 轮询 job 状态。

### 4.2 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/interpret` | 返回 `interpret.html` |
| `POST` | `/api/interpret/upload` | multipart：`file1`（必填）、`file2`（可选）；返回 `{ session_id, job_id }` |
| `GET` | `/api/interpret/jobs/{job_id}` | 任务状态 |
| `GET` | `/api/interpret/sessions` | 解读会话列表 |
| `GET` | `/api/interpret/sessions/{id}` | 会话详情 |
| `GET` | `/api/interpret/sessions/{id}/result` | 解读 + 模版完整 JSON |
| `GET` | `/api/interpret/sessions/{id}/sections/{node_id}` | 章节 Markdown（跳转原文） |

**`result` 响应结构**：

```json
{
  "interpretation": {},
  "templates": {},
  "source_files": ["file1.docx", "file2.pdf"]
}
```

### 4.3 环境依赖

解读阶段需要 LLM（与 `tender_insights` 一致）：

```bash
export LLM_API_KEY=sk-...
# 可选：LLM_PROVIDER, LLM_MODEL, LLM_BASE_URL
```

未配置时 interpret 阶段 job 失败，前端提示「请配置 LLM_API_KEY」。

---

## 5. 前端 UI

### 5.1 解读页（`interpret.html` + `interpret.js`）

**顶栏**：导航链接、双文件上传、解读会话下拉、「开始解读」按钮。

**进度区**：五段进度条（提取 1 → 提取 2 → 合并 → 解读 → 模版），当前阶段高亮；单文件时隐藏「提取 2」「合并」段。

**结果区 Tab 与卡片字段**：

| Tab | 数据来源 | 卡片字段 |
|-----|---------|---------|
| 废标项 | `disqualification_items` | 标题、摘要、触发条件、原文摘录、`section_path` |
| 得分项 | `scoring_items` | 标题、分值、权重、评分标准、原文摘录 |
| 风险 | `bid_risk_items` | 标题、严重度 badge、风险类别、摘要、原文摘录 |
| 目录要求 | `directory_requirements` | 标题、必填章节列表、是否强制 |
| 模版 | `templates.templates` | 模版名称、类型、所在章节 |

每张卡片：
- **查看原文** → 右侧滑出 panel，调用 sections API 渲染 Markdown
- **在切片预览中打开** → `/?session={id}&node={node_id}`

空 Tab 显示「未提取到相关项」。

### 5.2 切片预览页改动

- `index.html` 顶栏加同样导航链接
- `app.js` 支持 URL 参数 `?session=` 和 `?node=`，加载时自动选中

---

## 6. 错误处理

| 场景 | 处理 |
|------|------|
| 文件格式不支持 | 上传接口 400，前端 inline 提示 |
| pipeline 失败 | job `failed`，显示 stage 和 error |
| LLM 未配置 / 调用失败 | interpret 阶段 `failed`，提示检查 `LLM_API_KEY` |
| 合并校验失败 | merge 阶段 `failed`，提示工作区合并失败 |
| 重复点击「开始解读」 | 进行中禁用按钮 |

---

## 7. 测试

| 层级 | 覆盖 |
|------|------|
| 单元测试 | `workspace_merge.py`：单文件跳过、双文件偏移、node_id 去重、图片重名 |
| 集成测试 | 单文件上传 → FakeLLM → 验证 result API |
| 集成测试 | 双文件上传 → 验证 merge 后 content 长度与 outline 节点数 |
| API 测试 | upload 校验、job 轮询、result 404 |
| 手动冒烟 | 真实 LLM + 样例标书，五类 Tab 与原文跳转 |

LLM 测试通过 `FakeLLMClient` 注入，不依赖真实 API Key。

---

## 8. 实现备注

- `viewer/pyproject.toml` 增加 `tender-insights` editable 依赖
- `JobState.stage` 枚举扩展，或解读 job 使用独立 registry（实现时择一，保持 API 响应一致）
- 模版 Tab 中「预览链接」通过现有 assets 代理或 templates 目录下的文件路径提供
