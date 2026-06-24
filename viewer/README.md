# doc-chunk-viewer

本机调试 UI：上传 Word/PDF 或打开已有工作区 → 运行 doc_chunk pipeline → 左侧 outline 目录树 + 右侧章节 Markdown 浏览。

**定位**：内部开发工具，绑定 `127.0.0.1`，无鉴权，单用户本机使用。

---

## 安装

在仓库根目录执行（需先安装 `doc_chunk` 核心包）：

```bash
cd tender_skills
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pip install -e "./viewer[dev]"
```

---

## 启动

```bash
python -m viewer
# → http://127.0.0.1:8765
```

浏览器打开上述地址即可使用。

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DOC_CHUNK_VIEWER_DATA` | 数据根目录（工作区、会话索引） | `~/.doc-chunk-viewer/` |

数据目录结构：

```text
~/.doc-chunk-viewer/
├── sessions.json              # 最近 20 条切片会话索引
├── interpret_sessions.json    # 最近 20 条解读会话索引
├── uploads/<session_id>/        # 切片上传的原始文件
├── uploads/interpret/<session_id>/  # 解读上传的原始文件
└── workspaces/<session_id>/   # pipeline 产出（与 CLI 工作区结构相同）
```

### 招标解读（LLM）

解读页需要配置 LLM（与 `tender_insights` 一致）：

```bash
export LLM_API_KEY=sk-...
# 可选：LLM_PROVIDER, LLM_MODEL, LLM_BASE_URL
```

---

## 功能概览

| 能力 | 说明 |
|------|------|
| 上传新文件 | 支持 `.docx` / `.pdf`；后台跑 `extract → outline → tree → chunk`（跳过 refine 与 enrich） |
| 打开已有工作区 | 指定本地含 `outline.json` + `content.md` 的目录，直接浏览（适合 CLI 产出后调试） |
| 会话历史 | 本机记录最近 20 条处理记录，可快速切换 |
| Outline 树 | 左侧展示 1–8 级章节目录；`needs_review` 节点有警告标识；有子节点的父级可点击 ▸/▾ 展开/收起 |
| 章节 Markdown | 右侧按 outline 字符锚点从 `content.md` 截取并渲染 |
| 图片代理 | 工作区 `images/` 等资源通过 API 加载，不直接暴露文件路径 |
| Pipeline 进度 | 上传后轮询 job 状态，显示 extract / outline / tree / chunk 阶段 |
| **招标解读** | `/interpret` 页：上传 1～2 个招标文件 → 合并工作区 → 解读 + 模版提取 → 分类 Tab 展示 |

**不在 v1 范围**：chunk / document_tree 视图、LLM refine / enrich UI、在线编辑、导出、远程部署、法务审核 UI。

---

## 典型用法

### 1. 上传标书调试切片

1. 启动 viewer，点击「上传文件」
2. 选择 `.docx` 或 `.pdf`
3. 等待进度条完成（通常数秒，视文档大小而定）
4. 左侧点击章节节点，右侧查看对应 Markdown
5. 目录较深时，点击父节点左侧 ▸/▾ 收起子树，便于定位目标章节

### 2. 浏览 CLI 产出工作区

若已用 `doc-chunk pipeline` 生成工作区：

1. 点击「打开目录」
2. 输入工作区绝对路径（须含 `outline.json` 与 `content.md`）
3. 立即加载 outline 树，无需重跑 pipeline

### 3. 切换历史会话

顶栏会话下拉列表显示最近处理记录；切换后重新加载 outline，并尽量保持上次选中的节点。

### 4. 招标解读

1. 打开 `http://127.0.0.1:8765/interpret`
2. 选择文件 1（必填），可选补充文件 2
3. 点击「开始解读」，等待进度完成
4. 在 Tab 中查看废标项、得分项、风险、目录要求、模版
5. 卡片可「查看原文」或跳转切片预览深链接

---

## REST API

所有 API 前缀为 `/api`。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 返回静态单页 UI |
| `POST` | `/api/upload` | multipart 上传，返回 `{ session_id, job_id }` |
| `POST` | `/api/workspaces/open` | `{ "path": "/abs/path" }`，校验并注册会话 |
| `GET` | `/api/sessions` | 会话列表 |
| `GET` | `/api/sessions/{id}` | 会话详情 |
| `DELETE` | `/api/sessions/{id}` | 从索引移除（不删除工作区文件） |
| `GET` | `/api/sessions/{id}/outline` | 嵌套 outline 树 JSON |
| `GET` | `/api/sessions/{id}/sections/{node_id}` | 章节 Markdown 片段 |
| `GET` | `/api/sessions/{id}/assets/{path}` | 代理工作区静态资源（如 `images/xxx.png`） |
| `GET` | `/api/jobs/{job_id}` | pipeline 任务状态与进度 |
| `GET` | `/interpret` | 招标解读页 |
| `POST` | `/api/interpret/upload` | multipart：`file1`（必填）、`file2`（可选） |
| `GET` | `/api/interpret/jobs/{job_id}` | 解读任务状态 |
| `GET` | `/api/interpret/sessions` | 解读会话列表 |
| `GET` | `/api/interpret/sessions/{id}/result` | 解读 + 模版 JSON |
| `GET` | `/api/interpret/sessions/{id}/sections/{node_id}` | 章节 Markdown |

错误响应格式：`{ "detail": "..." }`（400 参数/格式错误，404 资源不存在）。

---

## 开发与测试

```bash
# 在仓库根目录
cd tender_skills
source .venv/bin/activate

# 全量 viewer 测试
python -m pytest viewer/tests/ -v

# 仅单元测试
python -m pytest viewer/tests/unit -v

# 仅 API 测试
python -m pytest viewer/tests/api -v
```

---

## 相关文档

| 文档 | 路径 |
|------|------|
| Viewer 设计规格 | [`docs/superpowers/specs/2026-06-16-doc-chunk-viewer-design.md`](../docs/superpowers/specs/2026-06-16-doc-chunk-viewer-design.md) |
| 招标解读页设计 | [`docs/superpowers/specs/2026-06-24-interpret-viewer-design.md`](../docs/superpowers/specs/2026-06-24-interpret-viewer-design.md) |
| 实现计划 | [`docs/superpowers/plans/2026-06-16-doc-chunk-viewer.md`](../docs/superpowers/plans/2026-06-16-doc-chunk-viewer.md) |
| doc_chunk CLI / API | [`README.md`](../README.md) |
