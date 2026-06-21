# 设计规格：Word 图片提取去重修复

**版本**: 1.0  
**日期**: 2026-06-21  
**状态**: 待实现  
**Feature ID**: `005-docx-image-dedup`  
**前置特性**: `001-document-extract-chunk`（extract 阶段）

---

## 1. 背景与问题

### 1.1 现象

从 Word 提取 inline 图片为 Markdown 时，出现两类互斥的问题：

1. **段落内重复**：同一段落在 `content.md` 中出现多条相同 `![](images/docx-img-NNN...)`，Word 视觉上只有一张图。
2. **跨位置丢失（回归）**：全局按 `r:embed` 去重后，同一图片在文档另一节（如「身份证明」表格）合法再次出现时不输出 Markdown 块。

### 1.2 实测证据（鼎信餐补标书）

源文件：`鼎信餐补标书.converted.docx`（223 MB）

| 节 | char 区间 | Word 视觉 | OOXML | 旧 extract | 当前 extract（全局去重） | 期望 |
|----|-----------|-----------|-------|------------|-------------------------|------|
| 四、法定代表人授权书 | 2767–3367 | 4 张图 | body#72 单段 8 blip / 4 唯一 rId | 8 条 Markdown | 4 条 ✓ | 4 条 |
| 五、法定代表人身份证明 | 3367–3633 | 2 张图（表格） | body#104 表格 2 blip（rId13/rId14） | 2 条 | **0 条 ✗** | 2 条 |

**body#72 段落内 blip 顺序**（8 节点，4 唯一 rId）：

```
rId11, rId12, rId11, rId12, rId13, rId14, rId13, rId14
```

每个 rId 对应两个 `w:drawing/wp:inline/a:blip` 节点（同结构 duplicate inline），Word 只渲染一份。

**跨节复用**：rId13/rId14（身份证 JPEG）在第四节与第五节表格各出现一次，属正常排版，不是段落内重复。

### 1.3 根因

| 层级 | 机制 | 正确处理方式 |
|------|------|--------------|
| 段落/元素内 | 同一 `w:p` OOXML 子树含多个 `a:blip` 共享 `r:embed` | **元素内**按 `r:embed` 去重后再 `add_image` |
| 跨段落/跨表格 | 同一 `r:embed` 在不同 body 元素再次出现 | **仍输出 Markdown 块**；磁盘文件只写一次 |

当前未提交改动在 `_register_docx_image` 用全局 `relationship_to_image_ref` 跳过第二次及以后的 `acc.add_image()`，误伤跨位置合法引用。

---

## 2. 目标与约束

### 2.1 产品目标

| # | 目标 |
|---|------|
| G1 | 段落内同一 `r:embed` 只输出 1 个 Markdown 图片块 |
| G2 | 跨位置同一 `r:embed` 每个文档位置输出 1 个 Markdown 块 |
| G3 | 磁盘上同一 `r:embed` 只保存 1 个文件 |
| G4 | `ExtractResult.image_count` = Markdown 图片块总数（选项 B） |
| G5 | `images/manifest.json` 每个 Markdown 块一条记录，`image_ref` 可重复 |
| G6 | `char_start`/`char_end` 锚点与 viewer 切片行为保持兼容 |

### 2.2 范围边界

**In Scope**

- `src/doc_chunk/extract/docx_extractor.py` 图片注册逻辑
- 单元测试 fixture 与鼎信节段回归断言
- 更新 `test_extract_docx_deduplicates_repeated_embed_references` 语义

**Out of Scope**

- 按 blob hash 去重（不同 rId、相同 bytes）
- PDF 图片提取
- viewer UI 改造

### 2.3 已确认决策

| 决策项 | 选择 |
|--------|------|
| 计数语义 | `image_count` = Markdown 图片块数；manifest 每块一条 |
| 文件存储 | 同一 `r:embed` 复用 `images/docx-img-NNN.ext` 路径 |
| 去重范围 | 仅元素内（段落 OOXML 子树）；不做全局 Markdown 抑制 |
| 回归样例 | 鼎信餐补 四/五 节 char 区间 |

---

## 3. 算法设计

### 3.1 保留：元素内 blip 去重

`_docx_element_image_embeds` 维持 `seen_relationship_ids`，在同一次 `element.iter()` 中对重复 `r:embed` 只返回一次。

`_docx_table_image_embeds` **移除** 表格级 `seen_relationship_ids`；保留 `id(cell._tc)` 合并单元格去重，单元格内仍走 `_docx_paragraph_image_embeds`。

### 3.2 修改：`_register_docx_image`

拆分「写文件」与「写 Markdown 块」：

```
on each (relationship_id, image_part) from paragraph/table walk:
  if relationship_id not in relationship_to_image_ref:
    image_count_file += 1
    save blob → images/docx-img-{file_n:03d}.ext
    relationship_to_image_ref[rid] = image_ref

  placement_n += 1   # equals returned image_count
  acc.add_image(image_ref, alt=f"docx-img-{placement_n:03d}")
  append ImageManifestEntry(..., source_block_index=current block)
  return placement_n
```

要点：

- **每次调用**都 `acc.add_image()`，不因 rId 已见过而跳过。
- **首次** rId 才写磁盘；后续复用已有 `image_ref`。
- `alt` 序号按**块放置顺序**递增（可与文件名序号不同，如 `docx-img-006` 指向 `docx-img-003.jpeg`）。
- 返回值 `image_count` = 已 emit 的 Markdown 块数。

### 3.3 数据流

```
body element (w:p / w:tbl)
  → element 内 embed 列表（已去重 blip）
  → for each embed:
       register: 文件首次落盘 / 路径复用
       accumulator: 始终 add_image
  → content.md + content.blocks.json + images/manifest.json
```

---

## 4. 鼎信回归期望

对 `鼎信餐补标书.converted.docx` extract 后：

| 断言 | 值 |
|------|-----|
| 四、授权书段 `![` 数量 | 4 |
| 五、身份证明段 `![` 数量 | 2 |
| 该两节合计 Markdown 块 | 6 |
| 该两节涉及唯一 rId | 4（rId11–14） |
| 磁盘文件（rId11–14） | 4 个 |

---

## 5. 测试计划

### 5.1 单元测试

| 测试 | 断言 |
|------|------|
| `test_extract_docx_deduplicates_repeated_embed_in_paragraph` | 单段双 blip 同 rId → 1 块、1 文件 |
| 更新 `test_extract_docx_deduplicates_repeated_embed_references` | deepcopy 段落（同 rId 两位置）→ **2 块、1 文件、image_count=2** |
| `test_extract_docx_reuses_file_across_paragraphs` | 同 PNG 两次 `add_picture` → 2 块、1 文件 |
| `test_extract_docx_table_reuses_rids_from_body` | 正文 rId + 表格同 rId → 各出块 |

### 5.2 集成 / 可选回归

- 环境变量 `DOC_CHUNK_DINGXIN_FIXTURE` 指向鼎信 docx 时，断言 §四/§五 图片块数（4 + 2）。
- 未设置则 skip，不阻塞 CI。

---

## 6. 错误处理

- `r:embed` 无对应 part：跳过，与现行为一致。
- 元素内 0 blip：不调用 register。

---

## 7. 非目标与已知限制

- **alt 与文件名不一致**：复用路径时 placement 序号继续递增；viewer 按 `image_ref` 加载，无功能影响。
- **manifest 重复 `image_ref`**：符合选项 B；消费方按 `source_block_index` 区分放置位置。
- **不同 rId 相同 bytes**：仍写多文件；不在本特性处理。

---

## 8. 实现清单（概要）

1. 重构 `_register_docx_image`：分离文件注册与块 emit。
2. 移除 `_docx_table_image_embeds` 表格级 rId 去重。
3. 更新/新增单元测试。
4. 可选：鼎信集成回归测试。
5. 对鼎信样例重跑 extract，人工 spot-check viewer 四/五 节。
