# 设计规格：doc_chunk 切片预览 Viewer

**版本**: 1.0  
**日期**: 2026-06-16  
**状态**: 已批准（brainstorming）  
**依赖**: `doc_chunk` 包（`001-document-extract-chunk`）  
**实现方案**: 方案 B — 独立顶层 `viewer/` 应用

---

## 1. 概述

### 1.1 背景

`doc_chunk` 已实现完整 CLI/库流水线（提取 → 目录树 → 文档树 → 分块 → 元数据），但 v1 需求明确排除 Web UI。本设计在**不修改核心库逻辑**的前提下，新增独立附属应用 `viewer/`，供内部开发者上传文档、跑切片流水线，并以「左侧 outline 目录树 + 右侧章节原文」方式浏览结果。

### 1.2 目标用户与定位

| 维度 | 决策 |
|------|------|
| 定位 | 内部开发调试工具 |
| 用户 | 技能/管线开发者，验证目录树与章节边界 |
| 部署 | 本机单用户，`127.0.0.1`，无鉴权 |
| 技术栈 | FastAPI + 单页静态（无 npm 构建） |

### 1.3 核心用户流程

1. **上传新文件**：选择 `.docx` / `.pdf` → 后台跑完整 pipeline（`skip_refine=True`, `skip_enrich=True`）→ 自动进入浏览视图
2. **打开已有工作区**：指定本地含 `outline.json` + `content.md` 的目录 → 直接浏览（适合 CLI 产出后调试）
3. **会话历史**：本机记录最近处理过的文档，快速切换

### 1.4 范围边界

**In Scope (v1)**

- 上传 `.docx` / `.pdf`
- Pipeline：`extract → outline → tree → chunk`（跳过 refine 与 enrich）
- 左侧：`outline.json` 章节目录树（1–8 级）
- 右侧：选中节点的章节原文 Markdown（按 outline 字符锚点从 `content.md` 截取）
- 会话历史（本地 JSON 持久化）
- 图片通过 API 代理加载（`images/` 相对路径）

**Out of Scope (v1)**

- chunk / document_tree 视图 Tab
- LLM outline refine 或 enrich UI
- 多用户、远程部署、权限控制
- 在线编辑 outline、导出功能
- `.doc` / `.docm` 直接上传（与库行为一致，需先转 docx）

---

## 2. 架构

### 2.1 方案选择

采用**方案 B：独立顶层 `viewer/` 应用**，通过 editable install 依赖同仓库 `doc_chunk`，边界清晰，不污染核心包。

```
tender_skills/
├── src/doc_chunk/              # 已有库，viewer 仅 import 公共 API
├── viewer/                     # 本设计范围
│   ├── pyproject.toml          # viewer 独立依赖声明，depends on doc-chunk (editable)
│   ├── README.md
│   ├── viewer/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app + 启动入口
│   │   ├── config.py           # 端口、数据目录
│   │   ├── routes/
│   │   │   ├── upload.py
│   │   │   ├── workspaces.py
│   │   │   ├── sessions.py
│   │   │   └── content.py
│   │   ├── services/
│   │   │   ├── pipeline.py     # 封装 doc_chunk.api.run_pipeline
│   │   │   ├── section_slice.py  # outline 节点 → markdown 片段
│   │   │   └── session_store.py
│   │   └── static/
│   │       ├── index.html
│   │       ├── app.js
│   │       └── style.css
│   └── tests/
```

### 2.2 与 doc_chunk 的集成

- **Pipeline**：调用 `doc_chunk.api.run_pipeline(path, output_dir, overwrite=True, skip_refine=True, skip_enrich=True, on_progress=...)`
- **工作区校验**：使用 `doc_chunk.workspace.layout.OutputWorkspace.open_existing`
- **章节截取**：复用 `anchor_planner` 中 `_section_end_char` 同等逻辑（按 `outline` 节点 `anchor.char_start` / `char_end` 从 `content.md` 切片，比标题正则更准确）

### 2.3 数据存储

默认数据根目录：`~/.doc-chunk-viewer/`（可通过环境变量 `DOC_CHUNK_VIEWER_DATA` 覆盖）

| 路径 | 用途 |
|------|------|
| `workspaces/<uuid>/` | 上传产生的工作区（与 CLI 输出结构相同） |
| `sessions.json` | 会话索引 |

**sessions.json 单条记录**：

```json
{
  "id": "uuid",
  "title": "文件名或目录名",
  "workspace_path": "/abs/path/to/workspace",
  "source_type": "upload | open",
  "status": "pending | running | success | failed",
  "created_at": "ISO8601",
  "opened_at": "ISO8601",
  "error": null
}
```

保留最近 **20** 条会话；超出时删除最旧条目（不删除工作区文件，仅移出索引）。

### 2.4 运行方式

```bash
cd tender_skills
pip install -e ".[dev]"          # doc_chunk
pip install -e "./viewer"         # viewer 及其依赖

python -m viewer                  # 默认 http://127.0.0.1:8765
```

绑定地址固定 `127.0.0.1`（仅本机访问）。

---

## 3. API 设计

### 3.1 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 返回 `static/index.html` |
| `POST` | `/api/upload` | multipart 上传，触发 pipeline，返回 `{ session_id, job_id }` |
| `POST` | `/api/workspaces/open` | `{ "path": "/abs/path" }`，校验并注册会话 |
| `GET` | `/api/sessions` | 会话列表 |
| `GET` | `/api/sessions/{id}` | 会话详情 + 状态 |
| `DELETE` | `/api/sessions/{id}` | 从索引移除（不删工作区文件） |
| `GET` | `/api/sessions/{id}/outline` | 嵌套树 JSON，供前端渲染 |
| `GET` | `/api/sessions/{id}/sections/{node_id}` | 章节 Markdown 片段 |
| `GET` | `/api/sessions/{id}/assets/{path:path}` | 代理 `images/` 等资源 |
| `GET` | `/api/jobs/{job_id}` | pipeline 任务状态与进度 |

### 3.2 Outline 树 API 响应

将 `outline.json` 扁平 `nodes` 转为嵌套结构：

```json
{
  "strategy": "toc",
  "nodes": [
    {
      "node_id": "n1",
      "title": "第一章 总则",
      "level": 1,
      "needs_review": false,
      "children": [
        {
          "node_id": "n2",
          "title": "1.1 范围",
          "level": 2,
          "needs_review": false,
          "children": []
        }
      ]
    }
  ]
}
```

### 3.3 Section 内容 API 响应

```json
{
  "node_id": "n2",
  "title": "1.1 范围",
  "level": 2,
  "section_path": ["第一章 总则", "1.1 范围"],
  "needs_review": false,
  "char_start": 1024,
  "char_end": 4096,
  "markdown": "## 1.1 范围\n\n本节适用于…"
}
```

**截取规则**：

1. `char_start` = `node.anchor.char_start`（缺失时回退到标题正则匹配）
2. `char_end` = 下一同级或更高级标题的 `char_start`，或 `content.md` 末尾（与 `anchor_planner._section_end_char` 一致）
3. 首标题前的内容作为独立「前言」节点（`level: 0`, `title: "前言"`），若 `content.md` 在第一个标题前有非空内容

### 3.4 Pipeline 异步执行

- 使用 `asyncio.to_thread` 包装同步 `run_pipeline`，避免阻塞事件循环
- `job_id` 映射到内存 dict（单进程调试工具，无需 Redis）
- 进度通过 `on_progress` 回调写入 job 状态；前端每 1s 轮询 `/api/jobs/{job_id}`

**Job 状态示例**：

```json
{
  "job_id": "uuid",
  "session_id": "uuid",
  "stage": "chunk",
  "message": "chunking document",
  "status": "running",
  "error": null
}
```

`stage` 枚举：`extract | outline | tree | chunk | done | failed`

### 3.5 错误响应

统一格式：`{ "detail": "人类可读错误信息" }`

| 场景 | HTTP |
|------|------|
| 不支持的文件格式 | 400 |
| 工作区缺少 `outline.json` 或 `content.md` | 400 |
| 会话不存在 | 404 |
| pipeline 执行失败 | 会话 `status=failed`，job `status=failed`，`error` 含异常信息 |

---

## 4. 前端设计

### 4.1 技术选型

- 单页 `index.html`，无构建步骤
- **Markdown 渲染**：marked.js（CDN）
- **样式**：手写 CSS（左右分栏、树形缩进）
- **逻辑**：原生 JavaScript（不强制框架；若需轻量响应式可用 Alpine.js CDN）

### 4.2 布局

```
┌─────────────────────────────────────────────────────────┐
│ [上传文件] [打开目录…]     会话: ▼ 招标书样例.docx        │
│ ████████░░░░  chunking…                                 │
├────────────────┬────────────────────────────────────────┤
│ ▼ 第一章 总则   │  ## 1.1 范围                           │
│   · 1.1 范围 ✓ │                                        │
│   · 1.2 定义   │  本节适用于…                            │
│ ▶ 第二章 …     │  ![图](通过 assets API 加载)           │
│                │                                        │
│ strategy: toc  │  char: 1024–4096 · needs_review: false │
└────────────────┴────────────────────────────────────────┘
```

### 4.3 交互行为

| 操作 | 行为 |
|------|------|
| 上传文件 | 创建会话 → 显示进度条 → 完成后加载 outline，选中首节点 |
| 打开目录 | 弹出路径输入（v1 用 `<input>` + 确认；不实现系统文件选择器） |
| 切换会话 | 重新加载 outline 树；保持上次选中 node_id（若仍存在） |
| 点击树节点 | 请求 section API，右侧渲染 Markdown |
| `needs_review` 节点 | 树节点旁显示 ⚠ 图标；底栏标注 |

### 4.4 静态资源

- FastAPI `StaticFiles` 挂载 `viewer/static/`
- 工作区图片不直接暴露文件路径，统一走 `/api/sessions/{id}/assets/images/xxx.png`

---

## 5. 依赖

### 5.1 viewer 新增 Python 依赖

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
python-multipart>=0.0.12
```

通过 `viewer/pyproject.toml` 声明，并 `depends on doc-chunk`（editable）。

### 5.2 根仓库 .gitignore 补充

```
.doc-chunk-viewer/
.superpowers/
```

---

## 6. 测试策略

| 层级 | 范围 |
|------|------|
| 单元 | `section_slice.py` 锚点截取；`session_store.py` CRUD；outline 嵌套转换 |
| API | FastAPI `TestClient`：打开夹具工作区 → outline/section/assets 端点 |
| 集成 | 上传 `tests/fixtures` 样例 docx → 等待 job 完成 → 验证树非空、section markdown 非空 |

不要求 E2E 浏览器测试（v1）。

---

## 7. 验收标准

| ID | Given | When | Then |
|----|-------|------|------|
| AC-1 | 有效 docx | 上传 | pipeline 成功，outline 树可渲染 |
| AC-2 | 有效 pdf | 上传 | 同上 |
| AC-3 | CLI 产出工作区 | 打开目录 | 无需重跑 pipeline 即可浏览 |
| AC-4 | 多次上传 | 查看会话列表 | 显示最近记录，可切换 |
| AC-5 | 选中 outline 节点 | 点击 | 右侧显示对应章节 Markdown，图片可加载 |
| AC-6 | `needs_review` 节点 | 浏览 | 树节点与底栏有警告标识 |
| AC-7 | pipeline 失败 | 上传损坏文件 | 会话状态 failed，错误信息可见 |

---

## 8. 后续扩展（非 v1）

- 右侧 Tab：原文 / 分块 / 元数据
- document_tree 视图
- `doc-chunk serve` 合并为统一 CLI 入口
- 系统原生文件/目录选择器（Electron 或 pywebview）

---

## 附录：Brainstorming 决策记录

| 问题 | 选择 |
|------|------|
| 工具定位 | A · 内部开发调试 |
| 左侧树 | A · outline 章节目录树 |
| 右侧内容 | A · 章节原文 Markdown |
| Pipeline | B · 完整切片，跳过 LLM 增强 |
| 工作区入口 | C · 上传 + 打开 + 会话历史 |
| 技术形态 | FastAPI + 单页静态（无构建） |
| 实现方案 | B · 独立顶层 viewer/ 应用 |
