# 设计规格：Word 表格提取增强（合并去重 + 三端消费）

**版本**: 1.0  
**日期**: 2026-06-17  
**状态**: 已实现  
**Feature ID**: `004-docx-table-extract`  
**前置特性**: `001-document-extract-chunk`（extract 阶段）

---

## 1. 背景与问题

### 1.1 现象

从 Word 提取表格为 Markdown 时，合并单元格导致列内容重复，例如：

```markdown
| 姓名 | 姓名 | 本项目工作角色 | 性别 | 性别 | 学历 | 学历 |
| --- | --- | --- | --- | --- | --- | --- |
| 刘敏 | 刘敏 | 开发工程师 | 男 | 男 | 本科 | 本科 |
```

文档中「姓名」仅出现一次，但提取结果重复两次。

### 1.2 根因

`docx_extractor._table_to_markdown` 直接遍历 `python-docx` 的 `row.cells`。当单元格存在横向合并（`w:gridSpan`）时，同一物理单元格会被返回多次。同文件中的 `_docx_table_image_parts` 已用 `id(cell._tc)` 去重，但表格文本转换未使用。

### 1.3 额外复杂性

招投标文档常见**人员双行表**（基本信息行 + 扩展信息行），以及纵向合并（`w:vMerge`）。仅做列去重不足以让 LLM 理解语义；标书生成需要保留物理合并结构以回写 Word。

---

## 2. 目标与约束

### 2.1 产品目标

| # | 目标 | 消费方 |
|---|------|--------|
| G1 | 修复合并单元格导致的重复列 | 全员 |
| G2 | `content.md` 保留去重 Markdown 表格，viewer 无需改动 | doc-chunk viewer |
| G3 | 提供 LLM 友好结构化文本（人员表合并为记录） | tender_insights / agent |
| G4 | 提供可回写 Word 的物理网格（保留 colspan/rowspan） | 标书生成（后续） |
| G5 | 块级索引与 `char_start`/`char_end` 锚点保持兼容 | outline / chunk / linkage |

### 2.2 范围边界

**In Scope**

- `.docx` / `.docm` extract 阶段表格处理
- 新增 `tables/` 工作区侧车与 schema
- `content.blocks.json` schema 1.1 扩展（`table_ref`）
- 公共 API：`load_table_model`、`substitute_tables_for_llm`
- 单元测试与人员双行表 fixture

**Out of Scope（本特性）**

- PDF 表格提取改造
- `table_to_docx` 完整实现（仅定义契约与占位模块）
- viewer UI 改造（继续渲染 `content.md` Markdown）
- tender_insights 全量切换（提供工具函数，技能迁移可后续）

### 2.3 已确认决策

| 决策项 | 选择 |
|--------|------|
| 主消费方 | LLM / Agent |
| 复杂表格 | 支持人员双行表等招投标常见版式 |
| 人工查看 | doc-chunk viewer（读 `content.md`） |
| 产物架构 | 方案 B：`content.md` + `tables/` 侧车 |
| Word 回写保真度 | C：尽量还原源文档合并与双行版式 |

---

## 3. 整体架构

### 3.1 数据流

```
Word 表格 (OOXML)
    → TableExtractor
         ├─ 物理网格解析（gridSpan / vMerge / tblGrid）
         ├─ 逻辑视图派生（去重列）
         ├─ 版式分类（personnel_dual_row / simple / key_value / fallback）
         └─ 三端序列化
              ├─ content.md          → Markdown 表格（逻辑视图）
              ├─ tables/t{NNNN}.json → 完整侧车
              └─ content.blocks.json → table 块 + table_ref
```

### 3.2 工作区布局

```
workspace/
├── content.md
├── content.blocks.json       # schema 1.1
├── tables/
│   ├── index.json
│   ├── t0003.json
│   └── ...
└── manifest.json             # 登记 tables/
```

### 3.3 模块划分

| 模块 | 路径 | 职责 |
|------|------|------|
| `TableGridParser` | `src/doc_chunk/extract/table_grid.py` | OOXML → 物理网格 |
| `TableLayoutClassifier` | `src/doc_chunk/extract/table_layout.py` | 版式识别 + record_groups |
| `TableSerializer` | `src/doc_chunk/extract/table_serialize.py` | 生成 markdown / llm_text |
| `TableSidecarWriter` | `src/doc_chunk/extract/table_sidecar.py` | 写 tables/ 与 index |
| `table_model` | `src/doc_chunk/models/table_model.py` | Pydantic schema |
| `table_access` | `src/doc_chunk/table/access.py` | 加载、LLM 切片替换 |
| `table_to_docx` | `src/doc_chunk/convert/table_to_docx.py` | 契约 + 占位（后续实现） |

---

## 4. 物理网格与合并还原

### 4.1 OOXML 解析规则

直接读取 `w:tbl` 下每行 `w:tr` 的 `w:tc`：

| XML | 字段 | 说明 |
|-----|------|------|
| `w:gridSpan/@w:val` | `colspan` | 默认 1 |
| `w:vMerge/@w:val` | `vmerge` | `restart` / `continue` / null |
| `w:tblGrid/w:gridCol` | `grid_width` | 物理列数 |
| 单元格文本 | `text` | 段落合并，换行替换为空格 |

`vmerge: continue` 的格子不出现在行的 `cells` 列表；`restart` 锚点格带计算后的 `rowspan`。

每行满足：`sum(cell.colspan for cell in row.cells) == grid_width`。

### 4.2 逻辑视图

从物理网格派生 `logical_rows`：每个锚点格保留，`colspan > 1` 时 Markdown 只输出一列（文本不重复）。

示例：

```
物理: 姓名(colspan=2) | 角色 | 性别(colspan=2) | 学历(colspan=2)
逻辑: 姓名 | 角色 | 性别 | 学历
```

- `content.md` 与 `TableSidecar.markdown` 使用逻辑视图
- `grid` 字段保留物理网格，供 Word 回写

### 4.3 人员双行表识别

`layout_type: personnel_dual_row` 当且仅当：

1. 逻辑行数 ≥ 4 且为偶数
2. 奇数行（0-index: 0, 2, 4…）≥50% 单元格匹配人员字段词表（姓名、性别、学历、角色、职务等）
3. 偶数行 ≥50% 单元格匹配扩展字段词表（级别、年龄、毕业学校、从业年限、资质证书等）
4. 相邻两行逻辑列数相同

输出 `record_groups: [[0,1], [2,3], ...]`，将两行字段合并为 `records` 中的一条记录。

### 4.4 其他版式

| layout_type | 条件 | llm_text 格式 |
|-------------|------|---------------|
| `simple` | 首行为表头，其余为同质数据行 | `【表格:列表】` + `--- 行 N ---` |
| `key_value` | 逻辑列数 = 2，≥ 2 行 | `【表格:键值】` + `字段: 值` |
| `fallback` | 不满足以上 | `【表格:原始】` + 逻辑行文本 |

---

## 5. 侧车 Schema（`tables/t{NNNN}.json`）

```json
{
  "schema_version": "1.0",
  "block_index": 3,
  "layout_type": "personnel_dual_row",
  "grid_width": 7,
  "grid": {
    "rows": [
      {
        "cells": [
          {"text": "姓名", "colspan": 2, "rowspan": 1, "vmerge": null},
          {"text": "本项目工作角色", "colspan": 1, "rowspan": 1, "vmerge": null},
          {"text": "性别", "colspan": 2, "rowspan": 1, "vmerge": null},
          {"text": "学历", "colspan": 2, "rowspan": 1, "vmerge": null}
        ]
      }
    ]
  },
  "logical_rows": [
    ["姓名", "本项目工作角色", "性别", "学历"],
    ["刘敏", "开发工程师", "男", "本科"]
  ],
  "markdown": "| 姓名 | 本项目工作角色 | 性别 | 学历 |\n| --- | --- | --- | --- |\n| 刘敏 | 开发工程师 | 男 | 本科 |",
  "llm_text": "【表格:人员信息】\n--- 记录 1 ---\n姓名: 刘敏\n...",
  "record_groups": [[0, 1]],
  "records": [
    {
      "姓名": "刘敏",
      "本项目工作角色": "开发工程师",
      "性别": "男",
      "学历": "本科",
      "级别": "高级Java工程师",
      "年龄": "35",
      "毕业学校": "承德石油学院",
      "从业年限": "9+",
      "资质证书": "毕业证书、计算机技术与软件专业技术资格证书"
    }
  ]
}
```

### 5.1 `tables/index.json`

```json
{
  "schema_version": "1.0",
  "tables": [
    {"block_index": 3, "path": "tables/t0003.json"}
  ]
}
```

### 5.2 `content.blocks.json` 扩展（schema 1.1）

`ContentBlockRecord` 新增可选字段：

```python
table_ref: str | None = None  # e.g. "tables/t0003.json"
```

`schema_version` 升级为 `"1.1"`。无 `table_ref` 的旧 table 块视为仅有 Markdown（向后兼容读取）。

---

## 6. 下游改造

### 6.1 extract 阶段（`docx_extractor.py`）

- 将 `_table_to_markdown` 替换为调用 `TableExtractor.extract(table, block_index)`
- `BlockAccumulator.add_table` 扩展为 `add_table(markdown, *, table_ref: str | None)`
- extract 结束时写 `tables/index.json`，manifest 登记 `tables/`

### 6.2 `blocks_builder.py`

- 行为不变：仍用 `^\|.+\|$` 识别 `content.md` 中的 Markdown 表格
- `ChunkBlock.text` 保持 Markdown（与 viewer / chunk.markdown 一致）

### 6.3 LLM 切片替换（`doc_chunk.table.access`）

新增 `substitute_tables_for_llm(content_md, blocks) -> str`：

1. 找出切片范围内 `block_type == "table"` 且含 `table_ref` 的块
2. 按 `char_start`/`char_end` 将 `content_md` 中对应 Markdown 表格替换为 `llm_text`
3. 无 `table_ref` 时保留原 Markdown（旧工作区兼容）

`tender_insights` 的 `_slice_node_markdown` 在调用 LLM 前套一层此函数（后续 PR，本特性提供 API）。

### 6.4 chunk.blocks 扩展（可选，P1）

`ChunkBlock` 可增加 `table_ref: str | None`，使 blocks_v1 消费方能定位侧车。本特性 P0 不强制改 chunk schema；适配层可通过 `content.blocks.json` 反查。

### 6.5 viewer

无改动。继续从 `content.md` 切片并用 `marked` 渲染 Markdown 表格。

### 6.6 Word 回写契约（`table_to_docx`，后续实现）

```python
def render_table_to_docx(document: Document, grid: TableGrid, *, records: list[dict] | None = None) -> Table:
    """按物理 grid 建表并 merge；records 提供时仅更新格内文本，不改合并结构。"""
```

标书生成流程：加载 `tables/t{NNNN}.json` → 可选修改 `records` → `render_table_to_docx`。

---

## 7. 降级与错误处理

| 场景 | 行为 |
|------|------|
| OOXML 解析失败 | 回退现有 `row.cells` 遍历 + `id(_tc)` 行内去重；`layout_type: fallback`；写 warning 到 `ExtractResult.warnings` |
| 版式识别不确定 | `layout_type: fallback`；`llm_text` 用逻辑行；`grid` 仍尽量保留物理结构 |
| 空表 | 跳过，不写侧车 |
| 旧工作区无 `tables/` | `substitute_tables_for_llm` 透传 Markdown |
| 表格含图片 | 图片提取逻辑不变（`_docx_table_image_parts`）；图片块仍单独写入 content |

---

## 8. 测试计划

### 8.1 Fixture

| Fixture | 覆盖 |
|---------|------|
| `merged_colspan.docx` | 横向合并去重 |
| `personnel_dual_row.docx` | 人员双行表（用户样例结构） |
| `vertical_merge.docx` | 纵向合并 rowspan |
| `simple_table.docx` | 普通表头+数据行 |

### 8.2 单元测试

- `TableGridParser`：物理/逻辑网格正确性
- `TableLayoutClassifier`：版式分类与 record_groups
- `TableSerializer`：markdown / llm_text 快照
- `substitute_tables_for_llm`：替换区间与锚点不漂移
- 回归：`test_extract_docx_writes_markdown` 更新断言（去重后列数）

### 8.3 契约测试

- extract 后 `tables/index.json` 与 `content.blocks.json` 的 `table_ref` 一致
- `char_start`/`char_end` 仍指向 `content.md` 中 Markdown 表格

---

## 9. 实现分期

| 阶段 | 内容 |
|------|------|
| **P0** | 物理网格解析、逻辑 Markdown、侧车写入、合并去重、人员双行 llm_text、`substitute_tables_for_llm` API |
| **P1** | `table_to_docx` 实现、tender_insights 接入 LLM 替换、chunk.blocks `table_ref` |
| **P2** | PDF 表格、更多版式启发式、标书生成端到端集成测试 |

---

## 10. 非目标与风险

- **Markdown 不表达 colspan**：viewer 看到去重列，版式简化；完整版式仅在 Word 回写时还原。已接受。
- **版式启发式误判**：fallback 保证不丢数据；warnings 可观测。
- **schema 1.1 迁移**：新 extract 写 1.1；旧消费方忽略 `table_ref` 仍可用 Markdown。
