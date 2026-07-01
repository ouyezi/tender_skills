# Viewer 切片预览 — 文档资产列表面板设计

**日期**: 2026-07-01  
**状态**: 已定稿，待实现  
**关联**: [doc-chunk-table-assets-design](./2026-07-01-doc-chunk-table-assets-design.md)、[doc-chunk-viewer-design](./2026-06-16-doc-chunk-viewer-design.md)

---

## 1. 背景与目标

### 1.1 问题

切片预览页（`viewer/` `/`）当前仅支持左侧 outline 树 + 右侧章节 Markdown。文档中的**图片**与**表格**虽已在 extract 阶段产出 manifest / 侧车（见 table assets 特性），但调试 UI 无法：

- 浏览全文档资产列表及引用 ID
- 查看图片详情或下载表格 Word
- 从资产跳转到对应章节并在正文中定位

### 1.2 目标

1. 在切片预览页**左侧 outline 下方**展示全文档图片、表格资产列表
2. 引用 ID 为工作区路径（`images/...`、`tables/tNNNN.json`）
3. **查看详情**：图片弹层预览；表格下载 `.docx`（侧车即时渲染）
4. **点击行**：跳转 outline 章节 + 正文高亮该资产

### 1.3 已确认决策

| 决策项 | 选择 |
|--------|------|
| 布局 | 左侧 outline 下方固定资产面板（方案 B） |
| 引用 ID | 工作区路径 |
| 详情交互 | 图片 modal；表格 download docx |
| 行点击 | 跳转章节 + 高亮（方案 C） |
| 核心库边界 | **方案 B**：doc_chunk 统一资产层 + viewer 导航/高亮 |

---

## 2. 范围

### 2.1 P0

- doc_chunk：`collect_document_assets()`、`export_table_ref_to_docx_bytes()`
- viewer：`GET /document-assets`、`GET /tables/.../export.docx`
- viewer：左栏资产面板、图片 modal、表格下载、跳转 + 高亮

### 2.2 P1

- URL 深链接 `?asset=` 参数
- extract 阶段为 images manifest 写入 `char_start`/`char_end`（减少 blocks 反查）

### 2.3 非目标

- interpret 页资产展示
- tk `asset_id` UUID 展示
- 表格在线预览
- 多用户 / 远程部署

---

## 3. 架构

### 3.1 职责划分

```
doc_chunk (media 层)
  collect_document_assets()     → 合并 images/tables manifest + blocks char 区间
  export_table_ref_to_docx_bytes() → 侧车 → docx 字节

viewer (services + UI)
  resolve_outline_node_for_char()  → char → outline_node_id
  GET /document-assets             → core + outline_node_id
  GET /tables/{ref}/export.docx    → core export
  app.js                           → 列表、modal、跳转、高亮
```

### 3.2 方案对比（摘要）

| 方案 | 说明 | 结论 |
|------|------|------|
| A | viewer 自行 merge manifest | 逻辑重复 |
| **B** | core 资产层 + viewer 导航 | **采用** |
| C | core 含 outline 反查 | outline 规则与 viewer 耦合过紧 |

---

## 4. doc_chunk 核心库

### 4.1 模块布局

```
src/doc_chunk/media/
├── __init__.py
├── models.py          # DocumentAssetEntry, DocumentAssetsFile
└── assets.py          # collect_document_assets

src/doc_chunk/convert/
└── table_export.py    # export_table_ref_to_docx_bytes
```

### 4.2 统一模型

```python
class DocumentAssetEntry(BaseModel):
    asset_type: Literal["image", "table"]
    ref: str                    # images/... 或 tables/tNNNN.json
    source_block_index: int | None
    char_start: int | None
    char_end: int | None
    preview: str | None         # 图片 file_name；表格 markdown_preview
    meta: dict[str, Any] = Field(default_factory=dict)


class DocumentAssetsFile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    images: list[DocumentAssetEntry] = Field(default_factory=list)
    tables: list[DocumentAssetEntry] = Field(default_factory=list)
```

### 4.3 `collect_document_assets(workspace) -> DocumentAssetsFile`

1. 读 `tables/manifest.json`（缺失则 `tables: []`）
2. 读 `images/manifest.json`（缺失则 `images: []`）
3. 读 `content.blocks.json`，按 `image_ref` / `table_ref` 补全 `char_start`/`char_end`
4. 映射为 `DocumentAssetEntry`；`meta` 保留类型特有字段（`content_type`、`layout_type` 等）
5. 各组内按 `char_start` 升序（缺失排末尾）

与现有 `collect_table_assets()` 关系：保留；`collect_document_assets` 内部可复用 tables 汇总逻辑。

### 4.4 `export_table_ref_to_docx_bytes(workspace, table_ref) -> bytes`

- `load_table_model` + 内存 `Document()` + `render_sidecar_to_docx`
- 不写临时文件；供 viewer `StreamingResponse` / `FileResponse` 使用
- 侧车不存在 → 抛出 `FileNotFoundError` 或项目统一 `WorkspaceError`

---

## 5. Viewer API

### 5.1 `GET /api/sessions/{session_id}/document-assets`

**流程**：

1. 加载工作区
2. 调用 `collect_document_assets(workspace)`
3. 读 `outline.json` + `content.md`
4. 对每条有 `char_start` 的资产调用 `resolve_outline_node_for_char(char_start, ...)`
5. 返回分组 JSON

**响应示例**：

```json
{
  "images": [
    {
      "asset_type": "image",
      "ref": "images/docx-img-001.png",
      "source_block_index": 5,
      "char_start": 1200,
      "char_end": 1250,
      "preview": "docx-img-001.png",
      "outline_node_id": "n003",
      "meta": { "content_type": "image/png", "byte_size": 102400 }
    }
  ],
  "tables": [
    {
      "asset_type": "table",
      "ref": "tables/t0003.json",
      "source_block_index": 8,
      "char_start": 2400,
      "char_end": 2800,
      "preview": "| 姓名 | 职务 | ...",
      "outline_node_id": "n004",
      "meta": { "layout_type": "simple", "row_count": 4, "col_count": 3 }
    }
  ]
}
```

### 5.2 `GET /api/sessions/{session_id}/tables/{table_ref}/export.docx`

- `table_ref`：URL 编码的相对路径，如 `tables/t0003.json`
- 响应：`application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- `Content-Disposition: attachment; filename="t0003.docx"`
- 404：侧车不存在

### 5.3 图片预览

复用现有 `GET /api/sessions/{session_id}/assets/{asset_path:path}`，前端 modal 内 `<img>` 加载。

### 5.4 `resolve_outline_node_for_char`（viewer 服务）

```python
def resolve_outline_node_for_char(
    char_pos: int,
    content_md: str,
    outline_tree: OutlineTree,
) -> str | None:
```

- 复用 `section_slice._build_node_heading_starts` 与各 section `[char_start, char_end)`
- `char_pos` 落在某 section 内 → 返回 `node_id`
- 落在第一个 heading 之前 → `PREFACE_NODE_ID`
- 无匹配 → `None`（前端禁用跳转）

---

## 6. 前端 UI

### 6.1 布局

左栏 `outline-aside` 纵向 flex：

- 上：`outline-tree`（`flex: 1`，可滚动）
- 下：`assets-panel`（约 35% 高度，min 160px，可滚动）

资产分「图片 (N)」「表格 (N)」折叠组；每行显示引用 ID、preview 摘要、「查看详情」按钮。

### 6.2 交互

| 操作 | 行为 |
|------|------|
| 查看详情 · 图片 | 打开 modal，加载 assets 代理 URL |
| 查看详情 · 表格 | 触发 export.docx 下载 |
| 点击行 | `focusAssetInDocument`：选章节 → 高亮 → scrollIntoView |
| 点击 outline 节点 | 清除资产高亮与 active 行 |
| 切换 session | 重新加载资产列表 |

### 6.3 正文高亮

- **图片**：匹配 `img[src*="{ref}"]`
- **表格**：优先匹配渲染后含占位符文本的节点；fallback 为 section 内第一个 `table` 元素（按 char 相对位置）
- 高亮 class：`.asset-highlight`（背景色 + 短暂 outline）

### 6.4 深链接（P1）

`/?session={id}&node={node_id}&asset={ref}` — bootstrap 后自动跳转并高亮。

### 6.5 改动文件

| 文件 | 改动 |
|------|------|
| `viewer/static/index.html` | assets-panel、image modal |
| `viewer/static/style.css` | 左栏分割、资产行、modal、高亮 |
| `viewer/static/app.js` | loadDocumentAssets、render、focus、modal |
| `viewer/routes/content.py` | document-assets、table export 路由 |
| `viewer/services/asset_navigation.py` | resolve_outline_node_for_char |
| `viewer/models.py` | DocumentAssetsResponse 等 |

---

## 7. 降级与错误处理

| 场景 | 行为 |
|------|------|
| 无 images manifest | `images: []` |
| 无 tables manifest | `tables: []` |
| 资产无 char 区间 | 列表展示；行点击提示「无法定位」 |
| 无 outline_node_id | 同上 |
| 表格侧车缺失 | 列表可展示；下载 404 |
| PDF 工作区 | 仅图片（若有 manifest） |
| pipeline 进行中 | 资产区显示「提取中…」 |

---

## 8. 测试计划

### doc_chunk

- `test_collect_document_assets` — 双 manifest + blocks char 合并
- `test_export_table_ref_to_docx_bytes` — 有效 docx 输出

### viewer

- `test_resolve_outline_node_for_char` — 前言、章节、边界
- `test_document_assets_api` — 集成 mock 工作区
- `test_index_static_assets_panel` — HTML/JS 含关键 hook

---

## 9. 实现分期

| 阶段 | 内容 |
|------|------|
| P0 | core media 层 + viewer API + 左栏 UI + modal + 下载 + 跳转高亮 |
| P1 | `?asset=` 深链接；images manifest char 字段 |

---

## 10. 依赖

- 表格侧车与 `tables/manifest.json`：见 [2026-07-01-doc-chunk-table-assets-design.md](./2026-07-01-doc-chunk-table-assets-design.md)
- 现有 viewer assets 代理与 section_slice 逻辑
