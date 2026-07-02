# 需求规格：outline anchor 与 viewer section char_start 对齐

**版本**: 1.0  
**日期**: 2026-07-02  
**状态**: Draft  
**Feature ID**: `anchor-viewer-alignment`  
**消费方**: `tender_knowledge`（知识录入章节预览、chunk enrich）、任意直接读取 `outline.json` anchor 的下游  
**相关 Issue**: tender_knowledge 预览 `content_md` 几乎为空（anchor 落在文首目录区）

---

## 1. 概述

### 1.1 背景

标书类 Word 文档解析后，`content.md` 文首通常包含：

- 封面、前言段落  
- **内嵌目录**（`# 标题\t页码` 形式，一行一个 TOC 条目）  
- 正文区真实章节标题（`### 2.1合同条款偏离表` 等）

当前流水线：

```text
outline/builder.py
  → enrich_outline_anchors()     # 写入 outline.json anchor.char_start
  → outline.json 落盘

viewer slice_section()
  → _build_node_heading_starts() # 运行时标题匹配，跳过 is_toc_entry_line
  → 返回 char_start / char_end
```

**问题**：两套逻辑不一致。

| 组件 | `char_start` 来源 | 标书样例表现 |
|------|-------------------|--------------|
| **viewer** `GET /sections/{node_id}` | 标题匹配 + 跳过 TOC | ✅ 指向正文标题（如 char≈5545） |
| **outline.json** `anchor.char_start` | `anchor_enricher` 模糊匹配 block | ❌ 常落在目录区（如 char≈60） |

根因在 `src/doc_chunk/outline/anchor_enricher.py` 的 `_find_block_for_title`：

- 全文顺序扫描 block，使用 `target in normalized` 模糊包含匹配  
- **未**调用 `is_toc_entry_line` 跳过目录行  
- **未**与 viewer 的 `sort_order` 顺序标题对齐逻辑一致  
- outline 标题常带粘连页码（如 `2.1合同条款偏离表12`），易与目录行 `## 合同条款偏离表\t12` 误配

tender_knowledge 导入时原样拷贝 `outline.json`，预览路径直接读取 `anchor.char_start`，导致章节预览仅有一行封面文字。

### 1.2 产品目标

| # | 目标 |
|---|------|
| G1 | 每个 outline 节点的 `anchor.char_start` **与 viewer 同 session 同 node_id 返回的 `char_start` 完全一致** |
| G2 | anchor **不得**落在文首内嵌目录区（`is_toc_entry_line` 为 true 的标题行） |
| G3 | viewer 与 `anchor_enricher` **共用同一套**章节起点定位逻辑（单一真相源） |
| G4 | 现有 `anchor_enricher` 能力保留：image/table 块锚点迁移到后续 paragraph/heading |
| G5 | 契约/单元测试覆盖 TOC 标书场景，防止回归 |

### 1.3 范围边界

**In Scope**

- 新增共享定位模块（建议 `src/doc_chunk/locate/heading_starts.py`）
- 修改 `src/doc_chunk/outline/anchor_enricher.py`
- 修改 `viewer/viewer/services/section_slice.py`（改为调用共享模块）
- 单元测试 + 与 viewer 对比的集成断言
- 文档与 changelog

**Out of Scope**

- 修改 outline 树的 `title` / `level` / `parent_id` / `sort_order` 生成策略  
- tender_knowledge 侧代码改动（消费方仅需重导文档）  
- 自动迁移历史已落盘 `outline.json`  
- 解决「正文多处完全同名同 level 标题且 sort_order 与出现顺序不一致」的极端场景（另开 issue）

### 1.4 方案决议

| 议题 | 决议 |
|------|------|
| 对齐标准 | **方案 A**：`outline.anchor.char_start` ≡ viewer `sections/{id}.char_start` |
| 实现路径 | 抽共享 `heading_starts` 模块；viewer 与 enricher 均调用 |
| `anchor.char_end` | 仍为标题 block 的 `char_end`；**章节终点**由下游按下一节点 `char_start` 或 viewer `char_end` 计算 |
| 兼容性 | **破坏性变更**（anchor 数值变化）；需重新解析文档 |

---

## 2. 问题证据（tender_knowledge 消费样例）

文档 ID：`de2c2bd7-5f7d-48bc-9a92-7103fcf89781`（餐补类标书，235 outline 节点）

节点 `n4`（标题 `2.1合同条款偏离表12`）：

| 来源 | char_start | 片段 |
|------|------------|------|
| `outline.json` anchor | **60** | `2025年生日福利预算\n\n投标/响应文件...`（封面/目录） |
| viewer `sections/n4` | **≈5545** | `### 2.1合同条款偏离表\n\n（如客户招标文件...` |
| 正文真实标题位置 | 5545 | 含完整偏离表表格 |

同文档前 15 个节点 `anchor.char_start < 200`，均落在文首目录簇；viewer 对 `n124` 等同理正确，outline anchor 仍指向目录区。

---

## 3. 技术方案

### 3.1 共享模块 `doc_chunk/locate/heading_starts.py`

从 `viewer/viewer/services/section_slice.py` 抽出以下能力（命名可调整，职责不变）：

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `parse_body_headings` | `content_md` | `list[Heading]` | 正则解析 `#` 标题；**跳过** `is_toc_entry_line` |
| `normalize_outline_title` | `title: str` | `str` | 去页码 tab 后缀、章节号前缀、中文枚举前缀（与 viewer `_normalize_title` 一致） |
| `build_node_heading_starts` | `OutlineTree`, `content_md` | `dict[str, int]` | 按 `sort_order` 贪心顺序匹配；`level` + normalize 标题相等 |
| `fallback_char_start` | `content_md`, `title`, `level` | `int \| None` | 单节点全文首个匹配（viewer 现有 fallback） |
| `section_char_range` | `tree`, `content_md`, `node_id` | `(start, end)` | start 来自 heading_starts；end 来自 `_section_end_by_heading`（与 viewer 一致） |

**依赖**：`doc_chunk.extract.promote_headings.is_toc_entry_line`（已有，禁止重复实现 TOC 判定）

### 3.2 修改 `anchor_enricher.py`

```text
enrich_outline_anchors(tree, blocks, content_md):

  # 保留：image/table 块 → 后续 paragraph 迁移（_relocate_non_paragraph_anchor）

  heading_starts = build_node_heading_starts(tree, content_md)

  for node in tree.nodes:
    if node.node_id in heading_starts:
      anchor.char_start = heading_starts[node.node_id]
      anchor.char_end   = 覆盖该 char_start 的 heading block 的 char_end
      anchor.block_index / block_start = 对应 heading block 的 index
    else:
      # 保留现有 _find_block_for_title fallback
      # 若仍失败：anchor 字段可为空，node.needs_review = true（若模型支持）

  return tree
```

**禁止**作为最终 `anchor.char_start` 的依据：

- 单独使用 `target in normalized` 模糊匹配到的**第一个** paragraph block（可作为 block_index 提示，但必须经 heading_starts 确认或 fallback 链）

### 3.3 修改 viewer `section_slice.py`

- 删除本地重复的 `_parse_headings` / `_build_node_heading_starts` / `_normalize_title`（若已迁入共享模块）  
- `slice_section` / `build_section_char_ranges` 改为 `from doc_chunk.locate.heading_starts import ...`  
- **对外 API 响应格式不变**

### 3.4 `char_end` 语义（不变更契约）

| 字段 | 语义 |
|------|------|
| `anchor.char_start` | 章节起点；**必须与 viewer 一致**（本需求验收核心） |
| `anchor.char_end` | 标题 block 在 `content.md` 中的结束偏移（通常仅标题行） |
| viewer `char_end` | 下一同级/上级标题起点，或文末；下游切片应优先此规则而非 `anchor.char_end` |

---

## 4. 匹配规则（冻结，与 viewer 当前行为一致）

1. 解析标题时跳过 `is_toc_entry_line(title)`（`标题\t页码`）  
2. 节点按 `(sort_order, node_id)` 排序；标题列表按文档顺序扫描；**贪心前进，不回头**  
3. 匹配条件：`node.level == heading.level` 且 `normalize_outline_title(node.title) == normalize_outline_title(heading.title)`  
4. 顺序匹配失败 → `fallback_char_start(content_md, node.title, level=node.level)`  
5. 仍失败 → 现有 block 匹配；再失败 → `char_start` 为空  

**标题 normalize 必须处理**：

- 粘连页码：`2.1合同条款偏离表12` ↔ 正文 `2.1合同条款偏离表`  
- 章节号前缀：`1投标函11` ↔ `# 投标函\t11`  
- tab 页码后缀：`## 合同条款偏离表\t12`（TOC 行本身应被 `is_toc_entry_line` 排除，不参与匹配）

---

## 5. 测试要求

### 5.1 新增 `tests/unit/test_anchor_enricher_toc_bid.py`

**Fixture**（可精简，须覆盖结构）：

```text
content.md =
  封面段落
  目录区（多行 # 标题\t页码）
  正文 # 服务偏离表
  正文 ### 2.1合同条款偏离表 + 表格
  正文 ### 2.2技术条款偏离表 + 内容
```

| 用例 | 断言 |
|------|------|
| `test_enrich_skips_toc_for_section_2_1` | `n_2_1.anchor.char_start` 指向正文 `### 2.1...`，且 `char_start >= first_body_heading_start` |
| `test_enrich_char_start_matches_viewer` | enrich 后 `anchor.char_start == slice_section(...).char_start` |
| `test_enrich_does_not_use_fuzzy_first_match_in_toc` | 目录区 char 范围内不得作为最终 anchor |

### 5.2 新增 `tests/unit/test_heading_starts_shared.py`

- viewer 与 `build_node_heading_starts` 对同一 fixture 输出一致  
- 父节点 `char_end`（viewer）包含子节正文  

### 5.3 回归

- `tests/unit/test_anchor_enricher.py` 全部通过  
- 现有 viewer section 相关测试通过  

### 5.4 可选集成（有样例时）

对 `output/zhongyin-canbu-v2` 或 tender_knowledge 文档 `de2c2bd7` 全量 outline 节点：

```python
for node in outline.nodes:
    assert node.anchor.char_start == slice_section(content_md, tree, node.node_id).char_start
```

---

## 6. 验收标准

1. **单元**：§5 全部通过  
2. **对照**：样例文档 `n4` anchor `char_start` ≈ 5545（非 60）  
3. **viewer 零差异**：同 session 任意 `node_id`，outline anchor 与 `sections/{id}` 的 `char_start` 相等  
4. **下游**：tender_knowledge 重新导入后，`GET .../preview` 返回含表格的完整 `content_md`（消费方验收，非本仓库 CI 必选项）

---

## 7. 发布与迁移

| 项 | 说明 |
|----|------|
| 版本 | 建议 minor bump |
| Changelog | 注明 `outline.json` `anchor.char_start` 语义变更，与 viewer 对齐 |
| 迁移 | 已解析文档需 **重新跑 doc-chunk 流水线**；不自动回写 |
| tender_knowledge | 重新 `import` / 替换 `outline.json` + `content.md` |

---

## 8. 实现顺序建议

1. 抽 `doc_chunk/locate/heading_starts.py` + 单测  
2. viewer `section_slice.py` 切到共享模块（行为不变，建立基线）  
3. `anchor_enricher.py` 写入 heading_starts 结果  
4. 新增 TOC 标书 fixture 测试  
5. 样例文档全量对比 + changelog  

---

## 9. 参考代码位置

| 路径 | 说明 |
|------|------|
| `src/doc_chunk/outline/anchor_enricher.py` | 当前 anchor 填充（待改） |
| `src/doc_chunk/outline/builder.py` | 调用 `enrich_outline_anchors` |
| `viewer/viewer/services/section_slice.py` | viewer 标题匹配（迁移来源） |
| `src/doc_chunk/extract/promote_headings.py` | `is_toc_entry_line` |
| `src/doc_chunk/chunk/planner.py` | `plan_chunks_from_anchors` 间接依赖 anchor 质量 |

---

## 10. 相关文档

- tender_knowledge：`docs/superpowers/specs/2026-07-02-entry-preview-anchor-slice-design.md`（消费方纯 anchor 预览；依赖本需求修复上游数据）  
- [`2026-06-15-doc-chunk-tk-integration-fixes.md`](./2026-06-15-doc-chunk-tk-integration-fixes.md)（anchor_enricher image/table 迁移，本需求在其基础上对齐 viewer）
