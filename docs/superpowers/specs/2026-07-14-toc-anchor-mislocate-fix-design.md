# 需求规格：TOC 目录区误定位修复（C + A + B）

**版本**: 1.0  
**日期**: 2026-07-14  
**状态**: 待实现  
**Feature ID**: `toc-anchor-mislocate-fix`  
**验收样例**: 湖南火电员工福利商城招标-标书（技术部分）.docx  
**相关**: [`2026-07-02-anchor-viewer-alignment.md`](./2026-07-02-anchor-viewer-alignment.md)（已落地：tab 页码 TOC 跳过与 viewer 对齐）

---

## 1. 概述与目标

### 1.1 背景

标书 Word 常含文首 **TOC 字段**。湖南火电技术标书中，目录行形如：

- `一、服务方案1`、`3.东福行业独家亮点9`（**粘连页码**，非 `标题\t页码`）
- 段落样式为 `toc 1` / `toc 2` / `toc 3`，并带 `HYPERLINK \l _TocXXXX`

大纲策略正确走 `toc`（约 32 节点），但标题定位仍可能先命中目录区：

1. `is_toc_entry_line` 只认 tab 页码，认不出粘连页码。
2. 正文存在同名标题；`heading_starts` 贪心匹配可能先落到目录区文本/被提升的标题。
3. 未利用 TOC 超链接指向的正文书签。

7/2 修复覆盖了餐补类 `标题\t页码` 场景，**不覆盖**本样例形态。

### 1.2 产品目标

| # | 目标 |
|---|------|
| G1 | outline / 章节切片的起点落在**正文标题**，不得落在文首 TOC 目录区 |
| G2 | 有 TOC 超链接时，优先用书签定位（方案 C） |
| G3 | 无书签或书签失效时，用目录区围栏（B）+ 扩展目录行识别（A）兜底 |
| G4 | 保持与 viewer 的 char_start 对齐契约（7/2）：同源定位逻辑 |
| G5 | 餐补等既有 TOC 回归测试继续通过 |

### 1.3 范围

**In Scope**

- DOCX：toc 样式跳过、粘连/点线目录行识别、`body_start` 围栏、TOC↔bookmark→block 定位
- `heading_starts` / `anchor_enricher` / `toc_docx` / `docx_extractor` / `is_toc_entry_line`
- 单元测试 + 湖南火电技术标验收（夹具或集成）

**Out of Scope**

- PDF 点线总目录的完整专项（A 行级启发式可顺带受益，不保证）
- 自动迁移历史 workspace 的 `outline.json`
- 修改用户 Word 源文件中的书签/TOC 字段
- 用 PAGEREF 页码推算字符位置

### 1.4 方案决议

| 议题 | 决议 |
|------|------|
| 策略组合 | **C + A + B 全部落地**（用户选择） |
| 单节点优先级 | 书签（C）→ 围栏内标题匹配（B + 现有 greedy）→ 扩展 TOC 行过滤（A）→ 现有 fallback |
| 对齐标准 | 应用上述优先级后，`outline.anchor.char_start` 仍与 viewer `sections/{id}.char_start` 一致 |
| 兼容性 | 破坏性（anchor 数值可能变）；需重跑流水线 |

---

## 2. 分层架构

```text
提取 DOCX
  ├─ A2: toc 样式段 → 不当 heading 写入 content.md
  └─ 普通标题/正文照旧
        ↓
大纲 toc_docx
  ├─ C: TOC → bookmark/_Toc → 正文 block（优先写入 anchor）
  └─ 产出 outline 树（标题去页码，沿用现有逻辑）
        ↓
定位 heading_starts / enrich_anchors
  ├─ 若已有 C 的可靠 anchor → 直接用
  ├─ B: body_start 围栏，匹配仅在其后
  └─ A1: 扩展 is_toc_entry_line 过滤目录行
```

| 层 | 职责 | 失败时 |
|----|------|--------|
| **C** | TOC 超链接/书签 → 正文档落 | 该节点回退 B+A |
| **B** | `body_start` 围栏，禁止匹配目录区 | `body_start=0`，仅靠 A |
| **A** | 识别目录行；提取不把 toc 写成 `#` | 保留现有 tab 规则 |

---

## 3. 方案 C：TOC 超链接 / 书签定位

### 3.1 解析步骤

1. 遍历带 `toc N` 样式（经 `styles.xml` 名映射，与现有 `build_toc_style_level_map` 一致）的段落，抽出标题（沿用 `_join_toc_text_parts` 去页码）。
2. 从同段或相邻 `instrText` 取 `HYPERLINK \l _TocXXXX`（或等价 bookmark 名）。
3. 定位 `w:bookmarkStart[@w:name="_TocXXXX"]`，映射到目标段落（书签所在或紧随的正文标题段）。
4. 将目标段落映射到提取后的 `block_index`（与 `content.blocks` 对齐：段落顺序稳定映射，或 enrich 阶段用文本+顺序解析）。
5. 写入 `OutlineNode.anchor`：优先 `block_index` / `block_start`；若已有 `content.md`，再填 `char_start` / `char_end`。

### 3.2 与流水线衔接

- 扩展 `extract_docx_toc_outline`，或新增旁路模块（如 `toc_bookmark_resolver`）在 outline 构建时填充 anchor。
- `enrich_outline_anchors`：若节点已有来自书签的可靠 `block_index`，**不以**目录区标题匹配覆盖；仅保留 image/table 等既有迁移。
- 单节点无 bookmark / 失效 / 对不上 block → 该节点走 B+A，不失败整棵树。

### 3.3 明确不做

- 不根据 PAGEREF 页码猜位置。
- 不修改 Word 源文件。

---

## 4. 方案 A：行识别 + 提取跳过

### 4.1 扩展 `is_toc_entry_line`（A1）

在现有 `标题\t页码` 之外：

| 形态 | 例 | 处理 |
|------|-----|------|
| 粘连页码 | `一、服务方案1`、`亮点9`、`概览12` | 与 `normalize_outline_title` 的 `_GLUED_PAGE_RE` 一致：整行长度 ≤120，且末尾为非数字字符后接 1–3 位页码；页码剥除后标题非空才判为目录行 |
| 点线引导 | `标题......12` / `标题…- 3 -` | 连续 `.` / `…` / `．` + 页码 |

误伤防护：标题本身合法以数字结尾时，优先依赖 **toc 样式（A2）** 与 **围栏（B）**；行级启发式为补充，非唯一依据。

### 4.2 提取时跳过 toc 样式（A2）

在 `extract_docx` 中识别 toc 样式：

- 不写入 `#` 标题。
- 写入普通 paragraph（不参与 promote 为 heading）。实现选取更简单路径即可。

效果：`parse_body_headings` 看不到目录行，从源头减少误匹配。

---

## 5. 方案 B：`body_start` 围栏

在 `heading_starts`（及 enrich 回退路径）中：

1. 计算 `body_start`（字符偏移）。**定位阶段只读 `content.md`，不再依赖 Word toc 样式**（样式信息仅在 A2 提取时使用）：
   - 优先：文首连续满足 `is_toc_entry_line` 的行/段落后的第一个位置（A2 后这些目录行多为普通段落，仍可用 A1 识别）；
   - 或：出现「目录」「总目录」类标题后，跳过紧随的目录行簇，取第一个非目录正文标题处；
   - 无法判定 → `body_start = 0`（与当前行为一致）。
2. `parse_body_headings` / 匹配循环：忽略 `char_start < body_start` 的候选。
3. 与 C 的关系：C 已给出可靠 anchor 的节点不再改写；未命中 C 的节点在围栏内做标题匹配。

---

## 6. 错误处理与兼容性

### 6.1 降级

- 单节点书签缺失/失效 → B+A，不中断 outline。
- 整份无 TOC 字段 / 无 toc 样式 → C 与 A2 空操作；B 算不出则 `body_start=0`。
- 书签落到 image/table → 沿用 `_relocate_non_paragraph_anchor`。
- 匹配仍疑似目录区（防御）→ `needs_review=True`，可选 warning（如 `anchor_in_toc_region`），不中断流水线。

### 6.2 兼容性

- **破坏性**：已落盘 `anchor.char_start` 可能变化；需重跑 extract → outline → chunk；不自动迁移历史。
- 7/2 契约保持：viewer 与 outline 共用定位结果（C 优先时二者同读最终 anchor / 同源 `heading_starts`）。
- 餐补（tab 页码 TOC）回归必须通过。
- 无 TOC 的普通 Heading 文档行为无明显回退。

---

## 7. 主要改动面

| 模块 | 变更 |
|------|------|
| `src/doc_chunk/extract/promote_headings.py` | 扩展 `is_toc_entry_line` |
| `src/doc_chunk/extract/docx_extractor.py` | 跳过 toc 样式作 heading |
| `src/doc_chunk/outline/toc_docx.py`（+ 可选 resolver） | TOC↔bookmark→block |
| `src/doc_chunk/locate/heading_starts.py` | `body_start` 围栏 |
| `src/doc_chunk/outline/anchor_enricher.py` | C 优先，不覆盖可靠书签 anchor |
| 测试 | 单测 + 湖南火电技术标夹具/集成 |

---

## 8. 验收标准

1. **湖南火电技术标**：抽查不少于 5 个原易错节点（如「一、服务方案」「2.兑换平台搭建方案」等），`anchor.char_start` / 章节切片落在正文，不在文首 TOC 行（如 `一、服务方案1`）。
2. 既有 TOC 对齐测试（餐补等）全绿。
3. 无 TOC 的普通 Heading 文档无显著回退。
4. 单元测试覆盖：粘连页码、点线引导、toc 样式跳过、`body_start` 计算、书签解析成功/失败降级。

---

## 9. 测试计划（摘要）

| 类型 | 内容 |
|------|------|
| 单元 | `is_toc_entry_line` 新形态；toc 样式不进入 heading；`body_start`；bookmark 名解析与缺失降级 |
| 回归 | `test_heading_starts_shared`、`test_anchor_enricher_toc_bid`、餐补集成 |
| 验收 | 湖南火电技术标：outline/slice 正文命中（夹具可裁剪 TOC+若干正文标题，或受控集成） |

---

## 10. 非目标与后续

- PDF 点线总目录完整修复：可另开 issue。
- 文中部重复「小目录」的极端布局：本设计以文首 TOC 簇为主；若出现再增强围栏启发式。
