# doc_chunk 表格资产提取与回插设计

**日期**: 2026-07-01  
**状态**: 已定稿，待实现  
**关联**: [docx-table-extract-design](./2026-06-17-docx-table-extract-design.md)、[doc-chunk-tk-integration](./2026-06-15-doc-chunk-tender-knowledge-integration.md)

---

## 1. 背景与目标

### 1.1 问题

doc_chunk 已在 DOCX extract 阶段为表格写入侧车（`tables/t{NNNN}.json`）并在 `content.blocks.json` 挂 `table_ref`，但与图片资产相比仍缺少：

- 统一的 **`tables/manifest.json`** 清单（供 tender_knowledge 注册 UUID）
- markdown / chunk.blocks 中的 **可追踪占位符**
- **`ChunkBlock.table_ref`** 与 `blocks_v1` 的 `asset_id` 映射
- 生成 docx 时的 **后置补丁 API**（按占位符插入物理表格）

### 1.2 目标

1. 提供 doc_chunk 方法，将文档中所有表格注册为**表格资产**，与 markdown 块一一关联
2. 支持 **tender_knowledge 适配层**注册 UUID（对齐 `document_media_assets`，场景 A）
3. 支持标书生成流程 **后置补丁**：markdown→docx 后按占位符插入物理表格（场景 B）
4. 渲染阶段继续保留 inline markdown 表格（展示简化可接受）

### 1.3 已确认决策

| 决策项 | 选择 |
|--------|------|
| 下游场景 | A（tk 落库）+ B（生成 docx 回插） |
| 回插策略 | 后置补丁（C），非 blocks 顺序渲染 |
| 定位机制 | markdown 隐藏占位符（A） |
| 实现路径 | 占位符 + markdown 双轨（方案 1） |
| P0 输入格式 | DOCX only |

---

## 2. 范围

### 2.1 P0

- extract 占位符写入、`tables/manifest.json`
- `collect_table_assets()`、`patch_docx_tables()`
- `ChunkBlock.table_ref`、`blocks_to_v1_json` 扩展
- `build_chunk_blocks` 占位符解析

### 2.2 P1

- `inject_table_placeholders()`（LLM 生成 markdown 补注入）
- `ContentChunk.table_refs[]`
- md→docx 占位符存活验证与 token fallback
- tender_knowledge 适配层集成测试

### 2.3 非目标

- PDF 表格侧车（P2）
- 修改 tender_knowledge 落库代码（适配层消费 manifest）
- 实现 markdown→docx 转换器
- 解决 markdown 表格 colspan 展示问题

---

## 3. 数据模型

### 3.1 与图片资产对照

| 维度 | 图片（现有） | 表格（本特性） |
|------|-------------|----------------|
| 资产文件 | `images/docx-img-001.png` | `tables/t0003.json` |
| 清单 | `images/manifest.json` | **`tables/manifest.json`** |
| 索引 | — | `tables/index.json`（保留） |
| markdown 锚点 | `![alt](images/xxx.png)` | **`<!-- table-ref:tables/t0003.json -->`** + markdown 表格 |
| content.blocks | `image_ref` + char 区间 | `table_ref` + char 区间 |
| chunk.blocks | `ChunkBlock.image_ref` | **`ChunkBlock.table_ref`** |
| chunk 索引 | `ContentChunk.image_refs[]` | **`ContentChunk.table_refs[]`**（P1） |
| blocks_v1 | `asset_id` + `image_ref` | **`asset_id` + `table_ref`** |

### 3.2 `tables/manifest.json`

```json
{
  "schema_version": "1.0",
  "tables": [
    {
      "table_ref": "tables/t0003.json",
      "source_block_index": 3,
      "layout_type": "personnel_dual_row",
      "row_count": 4,
      "col_count": 8,
      "char_start": 1024,
      "char_end": 1280,
      "markdown_preview": "| 姓名 | 本项目工作角色 | ..."
    }
  ]
}
```

- `table_ref`：主键，相对工作区根目录
- `source_block_index`：对应 `content.blocks.json` 的 `block_index`
- `layout_type` / `row_count` / `col_count`：来自 `TableSidecar`
- `char_start` / `char_end`：在 `content.md` 中的区间（含占位符 + markdown 表格）
- `markdown_preview`：前 120 字符

`tables/index.json` 保留；`collect_table_assets()` 从 index + blocks + sidecar 汇总生成 manifest。

### 3.3 `content.md` 写入格式

extract 阶段 `BlockAccumulator.add_table` 有侧车时：

```markdown
<!-- table-ref:tables/t0003.json -->
| 姓名 | 职务 |
| --- | --- |
| 张三 | 经理 |

```

- 有侧车 **MUST** 写占位符
- `char_start`/`char_end` 覆盖占位符 + markdown + 尾随空行

### 3.4 Chunk 模型扩展

```python
class ChunkBlock(BaseModel):
    type: Literal["paragraph", "table", "image"]
    text: str | None = None
    image_ref: str | None = None
    table_ref: str | None = None  # 新增

class ContentChunk(BaseModel):
    ...
    table_refs: list[str] = Field(default_factory=list)  # P1
```

`build_chunk_blocks` 逻辑：

1. 识别 `<!-- table-ref:... -->` → 记录 `pending_table_ref`
2. 紧随 `|...|` 行 → `type=table`，`table_ref=pending_table_ref`，`text=markdown`
3. 无占位符的旧表格 → `table_ref=null`

### 3.5 blocks_v1 导出

```python
def blocks_to_v1_json(
    blocks: list[ChunkBlock],
    *,
    image_ref_to_asset_id: dict[str, str] | None = None,
    table_ref_to_asset_id: dict[str, str] | None = None,
) -> str:
```

table 块输出：

```json
{
  "type": "table",
  "table_ref": "tables/t0003.json",
  "text": "| 姓名 | ...",
  "asset_id": "<uuid>"
}
```

无映射时仅 `table_ref` + `text`。

### 3.6 向后兼容

| 场景 | 行为 |
|------|------|
| 旧工作区无占位符 | `table_ref` 仍可从 blocks 读取；patch 需 `inject_table_placeholders` 或手动补占位符 |
| 无 `tables/manifest.json` | `collect_table_assets()` 按需生成 |
| 无侧车 table 块 | 仅 markdown，`table_ref=null`，不参与 patch |

---

## 4. API 设计

### 4.1 模块布局

```
src/doc_chunk/
├── models/tables_manifest.py     # TableManifestEntry, TablesManifest
├── table/
│   ├── assets.py                 # collect_table_assets
│   ├── patch.py                  # patch_docx_tables
│   └── placeholders.py           # TABLE_REF_COMMENT_RE, TABLE_REF_TOKEN_RE
├── extract/block_index.py        # add_table 写占位符
├── chunk/blocks_builder.py       # 解析占位符
└── convert/blocks_v1.py          # table_ref_to_asset_id
```

### 4.2 `collect_table_assets`

```python
def collect_table_assets(
    workspace: OutputWorkspace | Path,
    *,
    write_manifest: bool = True,
) -> TablesManifest:
```

1. 读 `content.blocks.json`，筛 `block_type == "table"` 且 `table_ref` 非空
2. 加载侧车，填充 manifest entry
3. 写入 `tables/manifest.json`（`write_manifest=True`）

调用时机：extract 末尾自动调用；旧工作区可手动补跑。

### 4.3 `patch_docx_tables`

```python
@dataclass
class PatchResult:
    patched_count: int
    skipped: list[str]
    warnings: list[str]

def patch_docx_tables(
    document: Document,
    workspace: OutputWorkspace | Path,
    *,
    table_refs: list[str] | None = None,
) -> PatchResult:
```

算法：

1. 扫描段落，匹配 `<!-- table-ref:tables/tNNNN.json -->` 或 fallback `⟦table:tables/tNNNN.json⟧`
2. 收集紧随的 markdown 表格段落（`| ` 开头）
3. `load_table_model` + `render_sidecar_to_docx` 在占位符位置插入物理表格
4. 倒序删除占位符 + markdown 段落

典型调用：

```python
doc = Document("generated.docx")
result = patch_docx_tables(doc, workspace)
doc.save("generated_with_tables.docx")
```

### 4.4 `inject_table_placeholders`（P1）

对 LLM 生成、未带占位符的 markdown，按 blocks char 区间补注入 comment。

### 4.5 占位符常量

```python
TABLE_REF_COMMENT_RE = re.compile(
    r"<!--\s*table-ref:(?P<ref>tables/t\d{4}\.json)\s*-->"
)
TABLE_REF_TOKEN_RE = re.compile(
    r"⟦table:(?P<ref>tables/t\d{4}\.json)⟧"
)
```

extract 统一写 comment；patch 两种均识别。

---

## 5. 数据流

```
DOCX → extract_docx
  ├─ tables/tNNNN.json
  ├─ content.md (占位符 + markdown)
  ├─ content.blocks.json (table_ref + char)
  └─ collect_table_assets → tables/manifest.json

content.md → chunk_document → chunk-NNNN.json (blocks[].table_ref)
chunk.blocks → blocks_to_v1_json → tk 落库 (asset_id)

LLM markdown → md→docx → patch_docx_tables → 物理表格 docx
```

---

## 6. 改造清单

| 文件 | 改动 |
|------|------|
| `block_index.py` | `add_table` 写占位符 |
| `docx_extractor.py` | 末尾 `collect_table_assets()` |
| `blocks_builder.py` | 解析 `table_ref` |
| `anchor_planner.py` / `planner.py` | P1: `table_refs[]` |
| `blocks_v1.py` | `table_ref_to_asset_id` |
| `workspace/layout.py` | `tables_manifest_path` |
| `api.py` manifest outputs | 登记 `tables_manifest` |

---

## 7. 错误处理

| 场景 | 行为 |
|------|------|
| 解析失败 / 空表 | 无侧车、无占位符、不进 manifest |
| patch 侧车缺失 | `skipped` 记录；保留原段落 |
| 占位符丢失 | 尝试 token fallback；warning `table_placeholder_lost:{ref}` |
| 占位符后无 markdown | 仍插入表格；删占位符 |
| 重复 patch | 幂等，`patched_count=0` |

Warnings：`table_sidecar_write_failed`、`table_manifest_orphan_ref`、`table_placeholder_lost`。

---

## 8. 测试计划

### 单元测试

- `test_table_placeholders.py` — regex、add_table、build_chunk_blocks
- `test_table_assets.py` — collect_table_assets
- `test_table_patch.py` — patch 往返、PatchResult
- `test_blocks_v1_convert.py` — table asset_id 映射

### 契约测试

- extract 后 content.md 含占位符，blocks/manifest 一致
- chunk.blocks 含 table_ref
- patch fixture 往返 snapshot

### Fixture

复用 `merged_colspan.docx`、`personnel_dual_row.docx`、`simple_table.docx`。

---

## 9. 实现分期

| 阶段 | 内容 |
|------|------|
| P0 | 占位符、manifest、collect、ChunkBlock.table_ref、blocks_v1、patch_docx_tables |
| P1 | inject_table_placeholders、table_refs[]、token fallback、tk 集成 |
| P2 | PDF 表格、端到端标书生成测试 |
