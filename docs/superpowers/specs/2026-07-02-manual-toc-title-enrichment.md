# 需求规格：Word TOC 字段 outline 提取（numeric styleId 修复）

**版本**: 1.1（修订：放弃文首手动目录方案，改为 Word TOC 字段）  
**日期**: 2026-07-02  
**状态**: Draft  
**Feature ID**: `word-toc-outline-extraction`  
**替代**: v1.0 `manual-toc-title-enrichment`（文首 `\t页码` 段落方案 **废弃**）

---

## 1. 概述

### 1.1 背景

餐补模板 `【大纲】餐补标书大纲模板6.16.docx` 重新提取后 outline 标题无序号（`投标函` 而非 `一、 投标函` / `2.1…`），根因 **不是** 缺少目录信息，而是 **Word TOC 字段提取失败**：

| 检查项 | 6.16 模板 | 当前 `toc_docx.py` 假设 |
|--------|-----------|-------------------------|
| `w:instrText` 含 `TOC` | ✅ `TOC \o "1-3" \h \u` | 作为门禁，已通过 |
| 目录段落 `w:pStyle/@w:val` | **`16` / `17`（数字 styleId）** | 仅匹配字面量 `toc1` / `toc2` |
| `styles.xml` 中 styleId 16 名称 | `toc 1` | **未读取** |
| 目录段落结构 | `HYPERLINK` + `PAGEREF` 字段 | 未使用（可辅助，非必须） |
| 提取结果 | `extract_docx_toc_outline` → **`None`** | fallback `heading_heuristic` → 无序号 |

**结论**：序号应来自 **Word TOC 字段渲染段落**（与 `超2-FY25` 等同源），而非 content.md 文首 Plain 目录行。

### 1.2 产品目标

| # | 目标 |
|---|------|
| G1 | 含 Word TOC 字段的 docx，`extract_docx_toc_outline` 成功返回 `strategy=toc` 的 outline |
| G2 | 节点 `title` 保留 TOC 中的章节序号（如 `一、 投标函`、`2.1 合同条款偏离表（…）`），页码已剥离 |
| G3 | 兼容旧模板：`pStyle` 为字面量 `toc1` 的文档行为不变 |
| G4 | 无 TOC 字段的文档仍 fallback `heading_heuristic`，本需求不改动 |

### 1.3 范围边界

**In Scope**

- 修改 `src/doc_chunk/outline/toc_docx.py`：从 `styles.xml` 解析 `toc N` 样式 → level 映射
- 单元测试 + 餐补 6.16 集成测试
- 更新/废弃 v1.0 文首 manual toc 计划

**Out of Scope**

- 解析 content.md 文首 Plain `\t页码` 行（**不做**）
- 回写 `content.md` 标题前缀
- PDF bookmark outline

### 1.4 方案决议

| 议题 | 决议 |
|------|------|
| 序号来源 | **Word TOC 字段**对应段落（`styles.xml` 命名为 `toc 1` / `toc 2` …） |
| level 推断 | `styles.xml` 中 `\btoc\s*(\d+)\b`（不含「TOC 标题」类样式） |
| pStyle 匹配 | `w:val` 先查 styleId 映射；保留 `^toc(\d+)$` 字面量 fallback |
| 标题拼接 | 沿用 `_join_toc_text_parts`（剥离末尾页码） |
| 门禁 | 仍要求 document.xml 存在 `TOC` instrText |

---

## 2. 技术方案

### 2.1 新增 `styles.xml` 映射

```python
def build_toc_style_level_map(styles_xml: bytes) -> dict[str, int]:
    """styleId (w:val) -> outline level, e.g. {'16': 1, '17': 2}."""
```

匹配规则（style `w:name/@w:val`）：

- ✅ `toc 1`, `toc1`, `TOC 2` → level 1, 2  
- ❌ `TOC 标题1`, `toc heading` → 跳过

### 2.2 修改 `extract_docx_toc_outline`

```text
1. 读 word/document.xml + word/styles.xml
2. has_toc_field 门禁（不变）
3. toc_levels = build_toc_style_level_map(styles.xml)
4. for each w:p:
     style_val = pStyle/@w:val
     level = toc_levels.get(style_val) or _TOC_STYLE_RE.match(style_val)
     if level: 拼接 title → OutlineNode
```

### 2.3 预期 6.16 模板结果（前 5 节点）

```text
n1  一、 投标函
n2  二、 服务偏离表
n3  2.1 合同条款偏离表（如客户招标文件有提供模板请使用客户的模板）
n4  2.2 技术条款偏离表（如客户招标文件有提供模板请使用客户的模板）
n5  三、 服务费一览表
```

（精确字符串以 `_join_toc_text_parts` 输出为准）

---

## 3. 测试要求

### 3.1 单元

- `build_toc_style_level_map`：numeric styleId + 字面量 toc1 双场景  
- `_join_toc_text_parts` 回归（已有）  
- synthetic docx：pStyle=`16` 且 styles.xml 命名 `toc 1`

### 3.2 集成

- 餐补 `6.16.docx`：`extract_docx_toc_outline` 非 None，`strategy=toc`，前节点含 `一、` / `2.1`  
- 重新 extract 后 `anchor.char_start` 与 viewer 仍一致（回归 anchor 对齐测试）

---

## 4. 验收标准

1. 6.16 模板 outline 策略为 **`toc`**，非 `heading_heuristic`  
2. outline 标题含 Word TOC 中的序号前缀  
3. 旧 fixture（字面量 `toc1`）测试仍通过  
4. 无 TOC 字段 docx 行为不变

---

## 5. 与 v1.0 手动目录方案的区别

| | v1.0（废弃） | v1.1（本规格） |
|---|-------------|----------------|
| 数据源 | content.md Plain `\t页码` 行 | Word TOC 字段 + styles.xml |
| 修改点 | 新 `manual_toc.py` | **`toc_docx.py`** |
| outline 策略 | 仍为 `heading_heuristic` + 补丁 | 恢复 **`toc`** |
