# doc_chunk 原表切片（mini-docx）设计

**日期**: 2026-07-01  
**状态**: 已定稿，待实现  
**关联**: [doc-chunk-table-assets](./2026-07-01-doc-chunk-table-assets-design.md)、[docx-table-extract](./2026-06-17-docx-table-extract-design.md)、[viewer-document-assets](./2026-07-01-viewer-document-assets-design.md)

---

## 1. 背景与目标

### 1.1 问题

当前表格 Word 导出与回插走 **grid 重建**（`render_sidecar_to_docx`）：保留 colspan/rowspan 与文本，但**不保留**源文档样式、列宽、边框、单元格内嵌图片/对象等。Viewer 下载 `.docx` 与 `patch_docx_tables()` 回插结果与原 Word 不一致。

侧车 JSON（`tables/t{NNNN}.json`）面向 LLM/结构化消费；`content.md` Markdown 展示简化是预期行为。缺口在 **Word 保真输出**。

### 1.2 目标

1. Extract 阶段为每张表生成**自包含**原表切片资产（mini-docx），不依赖源 docx 文件
2. Viewer 下载、标书生成 `patch_docx_tables()`、tender_knowledge 落库均可使用切片实现**完整保真**
3. 侧车 JSON 继续作为结构化数据源（LLM、查询、可编辑）；切片与 JSON **解耦**
4. 切片缺失或提取失败时，降级为现有 grid 重建，不阻断流程

### 1.3 已确认决策

| 决策项 | 选择 |
|--------|------|
| 消费场景 | Viewer 下载 + 生成回插 + tk 落库/可编辑 |
| 保真度 | 完整保真（样式、列宽、边框、单元格内嵌对象等） |
| 资产形态 | 自包含，不依赖源 docx |
| 实现方案 | 方案 1：单表 mini-docx（与 `images/` 资产模式对齐） |
| JSON 与 slice 关系 | 双轨；Word 输出只读 slice；编辑 JSON 不自动更新 slice |

---

## 2. 范围

### 2.1 P0

- Extract：`tables/t{NNNN}.docx` mini-docx 生成
- 侧车 JSON schema 1.1：`slice_ref`、`slice_status`
- `tables/manifest.json` schema 1.1 扩展
- `export_table_ref_to_docx_bytes()` 优先返回 slice
- `patch_docx_tables()` 优先 embed slice
- `collect_table_assets()` 汇总 slice 元数据
- 单元/集成测试与 fixture

### 2.2 P1

- tender_knowledge 适配层双 blob 落库（JSON + docx slice）
- Viewer export 响应头 `X-Table-Export-Mode: slice | rebuilt`

### 2.3 非目标

- JSON 编辑后 re-render slice（P2）
- PDF 表格切片
- markdown 展示 colspan 改造
- 修改 tender_knowledge 核心落库代码（适配层消费 manifest）

---

## 3. 架构与数据模型

### 3.1 双轨原则

| 轨道 | 文件 | 职责 |
|------|------|------|
| 结构化 | `tables/t{NNNN}.json` | LLM 文本、`logical_rows`、`grid`、`layout_type`；tk 查询与 JSON 编辑 |
| Word 保真 | `tables/t{NNNN}.docx` | 完整原表切片（自包含 mini-docx）；**所有 Word 输出的唯一保真来源** |

`table_ref` 主键仍指向 JSON，与现有 `content.blocks.json`、chunk、`blocks_v1` 兼容。消费 Word 时通过 JSON 或 manifest 解析 `slice_ref`。

### 3.2 工作区布局

```
workspace/
├── content.md
├── content.blocks.json
├── tables/
│   ├── index.json
│   ├── manifest.json          # schema 1.1
│   ├── t0003.json             # 结构化侧车 schema 1.1
│   ├── t0003.docx             # 原表切片（新增）
│   └── ...
└── manifest.json
```

### 3.3 侧车 JSON schema 1.1

在 schema 1.0 字段基础上新增：

```json
{
  "schema_version": "1.1",
  "block_index": 3,
  "slice_ref": "tables/t0003.docx",
  "slice_status": "ok",
  "layout_type": "personnel_dual_row",
  "grid_width": 8,
  "grid": { "rows": [] },
  "logical_rows": [],
  "markdown": "| ... |",
  "llm_text": "...",
  "record_groups": [],
  "records": []
}
```

| 字段 | 说明 |
|------|------|
| `slice_ref` | mini-docx 相对工作区路径；与 JSON 同 stem（`t0003`） |
| `slice_status` | `ok`：切片可用；`failed`：提取失败；`missing`：旧工作区或无切片 |

schema 1.0 工作区：`slice_ref` 省略或 `null`，`slice_status` 为 `missing`。

### 3.4 `tables/manifest.json` schema 1.1

```json
{
  "schema_version": "1.1",
  "tables": [
    {
      "table_ref": "tables/t0003.json",
      "slice_ref": "tables/t0003.docx",
      "slice_status": "ok",
      "slice_byte_size": 18432,
      "source_block_index": 3,
      "layout_type": "personnel_dual_row",
      "row_count": 4,
      "col_count": 8,
      "char_start": 1024,
      "char_end": 1280,
      "markdown_preview": "| 姓名 | ..."
    }
  ]
}
```

### 3.5 与图片资产对照

| 维度 | 图片（现有） | 表格 JSON | 表格 slice（本特性） |
|------|-------------|-----------|---------------------|
| 资产文件 | `images/docx-img-001.png` | `tables/t0003.json` | `tables/t0003.docx` |
| 自包含 | blob 即完整 | 结构化数据 | mini-docx 含闭包依赖 |
| manifest | `images/manifest.json` | `tables/manifest.json` | 同上，含 `slice_ref` |
| markdown 锚点 | `![alt](images/...)` | `<!-- table-ref:tables/t0003.json -->` | 不变（仍指向 JSON） |

---

## 4. Extract：mini-docx 生成

### 4.1 时机

`extract_docx` 中 `extract_table()` 写入 JSON 侧车后，同步调用 `extract_table_slice()`。

### 4.2 闭包收集算法

从源文档中的 `w:tbl` 深度遍历，收集完整保真所需 OPC 部件：

```
w:tbl (源文档)
  → 深度遍历收集引用
       ├─ 样式：tblStyle, pStyle, rStyle, tcStyle → styles.xml 闭包
       ├─ 编号：numId → numbering.xml 子集
       ├─ 主题/字体：theme.xml, fontTable.xml（按需）
       └─ 媒体：a:blip r:embed → word/media/* blob
  → 组装最小合法 OPC 包
       word/document.xml: 空 body + sectPr + 单个 w:tbl
       + 闭包 parts + [Content_Types].xml + rels
  → 写入 tables/t{NNNN}.docx
```

### 4.3 模块划分

| 模块 | 路径 | 职责 |
|------|------|------|
| `TableSliceExtractor` | `src/doc_chunk/extract/table_slice.py` | 从源 docx 定位单表并收集依赖闭包 |
| `MiniDocxBuilder` | `src/doc_chunk/table/slice_pack.py` | 组装自包含 mini-docx 并写入工作区 |
| `TableEmbedder` | `src/doc_chunk/table/embed.py` | 将 slice 注入目标 docx（patch 用） |

`TableSidecarWriter.write()` 扩展：接收 `slice_ref` / `slice_status`，写入 schema 1.1 JSON。

### 4.4 输出与失败处理

| 结果 | JSON | slice 文件 | `slice_status` |
|------|------|------------|----------------|
| 成功 | 正常 | `tables/t{NNNN}.docx` | `ok` |
| 闭包收集失败 | 正常（grid/markdown 仍可用） | 不写或删除半成品 | `failed` |
| 旧工作区 | schema 1.0 | 无 | `missing` |

失败时记录 warning：`table_slice_failed:t{NNNN}:<reason>`，写入 extract 日志通道。

---

## 5. Export / Patch 消费

### 5.1 Viewer 下载

`export_table_ref_to_docx_bytes(workspace, table_ref)`：

1. 加载 sidecar，读取 `slice_ref` 与 `slice_status`
2. `slice_status == ok` 且文件存在 → 直接返回 mini-docx 字节（用户用 Word 打开即见原表）
3. 否则 → 降级 `render_sidecar_to_docx()`（现有 grid 重建）
4. P1：响应头 `X-Table-Export-Mode: slice | rebuilt`

### 5.2 patch_docx_tables

`patch_docx_tables(document, workspace)` 对每个 `<!-- table-ref:... -->`：

1. 解析 `table_ref`，加载 sidecar
2. `slice_status == ok` → `TableEmbedder.embed_before(paragraph, slice_path)`
   - 打开 slice 与目标 docx 的 OPC package
   - 拷贝 tbl 所需 parts（styles 子集、media、numbering 子集）
   - 全局 remap relationship id，避免与目标 docx 冲突
   - 将 `w:tbl` 插入占位符段落之前
3. slice 不可用 → 降级 `render_sidecar_to_docx()`（现有行为）
4. 删除占位符段落及紧随的 markdown 表格段落

### 5.3 TableEmbedder 约束

- 合并操作在 OPC 层完成，非 python-docx 高层 API 拼接
- 冲突时记录 warning，单表 fallback 为 grid 重建，不阻断整文档 patch
- embed 后目标 docx 须为合法 OPC 包（可被 Word 打开）

---

## 6. Manifest 与 tender_knowledge

### 6.1 collect_table_assets()

从 sidecar 读取 `slice_ref`、`slice_status`；若 slice 文件存在则写入 `slice_byte_size`。manifest `schema_version` 升为 `1.1`。

### 6.2 tk 落库（适配层）

| 资产 | 落库内容 |
|------|----------|
| 结构化 | `tables/t0003.json` blob + metadata |
| Word 保真 | `tables/t0003.docx` blob |
| 索引 | manifest 条目（含 `table_ref` + `slice_ref`） |

工作区自包含；迁库后不依赖源 docx。`blocks_v1` 仍以 `table_ref`（JSON）为 `asset_id` 映射主键；slice 作为 table asset 的二进制附件由适配层注册。

---

## 7. 错误处理与降级

| 场景 | 行为 |
|------|------|
| slice extract 失败 | JSON 正常；`slice_status: failed`；export/patch 降级 grid 重建 |
| 旧工作区无 slice | `slice_status: missing`；降级 grid 重建 |
| patch embed 冲突 | warning + 单表 fallback 重建 |
| 单元格内嵌 OLE/复杂对象 | P0 尽力拷贝闭包；无法处理时 `failed` + warning |

降级路径 MUST 保持与当前实现行为一致，确保旧工作区与失败场景不回归。

---

## 8. 测试策略

| 层级 | 内容 |
|------|------|
| 单元 | `TableSliceExtractor` 闭包收集；`MiniDocxBuilder` 输出合法 docx；`TableEmbedder` rId remap |
| 集成 | fixture docx（合并单元格、样式、列宽、单元格内图片）→ extract → slice OOXML/视觉对比 |
| 回归 | 无 slice 旧工作区 export/patch 仍走 grid 重建 |
| API | `/tables/{ref}/export.docx` 有 slice 时返回 slice 字节 |

**验收标准**：对含样式、列宽、内嵌图的 fixture，Viewer 下载的 docx 与源 Word 打开该表视觉一致。

---

## 9. 向后兼容

| 场景 | 行为 |
|------|------|
| schema 1.0 侧车 | `slice_status: missing`；export/patch 走 grid 重建 |
| 无 `slice_ref` 字段 | 同 `missing` |
| `table_ref` / 占位符 | 不变，仍指向 JSON |
| `tables/index.json` | 保留；仅 JSON path，slice 通过 sidecar 关联 |

---

## 10. 实现顺序建议

1. `MiniDocxBuilder` + `TableSliceExtractor` + extract 集成
2. 侧车/manifest schema 1.1 + `collect_table_assets` 扩展
3. `export_table_ref_to_docx_bytes` 优先 slice
4. `TableEmbedder` + `patch_docx_tables` 优先 embed
5. fixture 测试与 viewer API 验证
6. P1：tk 适配层 + export 响应头
