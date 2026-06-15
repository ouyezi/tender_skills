# 需求规格：doc_chunk tender_knowledge 集成修复（002 后续）

**版本**: 1.1  
**日期**: 2026-06-15  
**状态**: 已实现  
**Feature ID**: `003-doc-chunk-tk-integration-fixes`  
**前置特性**: [`002-doc-chunk-tender-knowledge-integration`](./2026-06-15-doc-chunk-tender-knowledge-integration.md)（已实现主体能力）  
**消费方**: `tender_knowledge` 薄适配层（`doc_chunk_import_service`）

---

## 1. 概述

### 1.1 背景

Feature `002` 已落地：锚点分块、`document_tree.json`、`chunk.blocks`、`linkage.json`、`images/manifest.json`、`on_progress` 等。  
契约测试 53 项通过；餐补标书样例（`output/zhongyin-canbu-v2`）上 outline/chunk 强一致已验证。

在对接 `tender_knowledge` 落库前的复核中，发现 **`document_tree.json` 质量缺陷** 与若干 **消费方对齐缺口**，需在 `doc_chunk` 内修复，避免适配层承担复杂兜底。

### 1.2 产品目标

| # | 目标 |
|---|------|
| G1 | `document_tree.json` 节点 ID **全局唯一**，可安全映射为 DB 主键 |
| G2 | 每个 `outline.json` 节点在 `document_tree` 中均有对应 **heading 节点**（与 linkage 一致） |
| G3 | `blocks_v1` 导出与 tk 图片块字段对齐，适配层改动最小 |
| G4 | enrich 默认产出 `suggested_candidate_type`，减少 tk 二次规则推断 |
| G5 | 回归样例与契约测试覆盖上述场景，防止餐补级大文件回退 |

### 1.3 范围边界

**In Scope**

- `src/doc_chunk/tree/builder.py` 及关联模型
- `src/doc_chunk/outline/anchor_enricher.py`（锚点落在非段落块时的处理）
- `src/doc_chunk/convert/blocks_v1.py`
- `src/doc_chunk/metadata/`（候选类型规则）
- `src/doc_chunk/linkage/builder.py`（全覆盖 entry + tree 引用）
- `chunk` 阶段 `chunks/index.json` 写入 `document_tree_node_id`
- 契约 / 单元 / 集成测试；`tests/fixtures/` 黄金样例

**Out of Scope**

- tender_knowledge 数据库写入与适配层实现（仅定义消费契约）
- 恢复 tk 领域规则（内嵌附件、伪标题过滤等）
- 模板解析 `extract_fixed_paragraph_materials`

### 1.4 Clarifications（Session 2026-06-15）

| # | 主题 | 决定 |
|---|------|------|
| 1 | R2 范围 | **方案 A + B**：`anchor_enricher` 前移锚点 + `build_document_tree` 合成缺失 heading |
| 2 | 合成 heading 排序 | 按 `source_block_index` 插入，位于同 block 的 body 节点**之前** |
| 3 | 重复 `block_start` | 允许多 outline 共享；各合成独立 heading；manifest 警告 `outline_duplicate_anchor:{block_start}` |
| 4 | linkage 覆盖 | 每个 outline 必有 entry；无 chunk 时 `chunk_ids=[]`，`document_tree_node_ids` 仍非空 |
| 5 | flat_fallback 例外 | 仅 `strategy == "flat_fallback"` **且** `len(outline.nodes) == 1` 时放宽 R2/R3 |
| 6 | R5 enrich | 扩展默认 `chapter_taxonomies` + 关键词直映射 `suggested_*`；规则支持 **`ignore`** |
| 7 | R4 blocks_v1 | 有映射时 `asset_id` + `image_ref` 双字段；无映射仅 `image_ref`；工作区 `chunk.blocks` 不变 |
| 8 | `chunks/index.json` | **必写** `document_tree_node_id`（linkage 主 heading）；不一致则 manifest warning |
| 9 | R6 fixture | 两个：`outline_anchor_on_image.docx` + `outline_anchor_on_table.docx` |
| 10 | 方案 B 搜索 | 向后搜至下一 outline 的 `block_start`，取首个 paragraph 或标题匹配块 |
| 11 | NF1 性能基线 | 见 §4.1（E2E wall time，3 次中位数，`T_003 <= 1.2 * T_base`） |
| 12 | Plan Sync | 见 §5.1（003 PR 中修正 plan 过时表述，标注 `[Partially Completed in 002 / 003 Refactored]`） |

---

## 2. 问题证据（餐补样例 `zhongyin-canbu-v2`）

| 指标 | 实测值 | 期望 |
|------|--------|------|
| `outline.json` 节点数 | 173 | — |
| `linkage.json` 条目数 | 173 | 与 outline 一致 |
| `chunks/index.json` 条数 | 175 | outline + Preface + 续切块（可接受） |
| `document_tree` heading 且含 `outline_node_id` | **157** | **173** |
| `document_tree` **重复 `node_id`** | **9 处**（如 `t0001`） | **0** |
| outline 锚在 image/table 块上的节点 | **16** | 0 或均有 heading 兜底 |
| enrich `suggested_candidate_type` | 多为 `null` | 有规则命中时应非空 |

**重复 ID 根因（代码审查）**：`tree/builder.py` 中 heading 使用 `heading_counter`、正文使用 `node_counter`，两套序号均格式化为 `t{nnnn:04d}`，会撞号。

**heading 缺失根因**：`build_document_tree` 仅在 `block.block_type in {"heading", "paragraph"}` 且 `outline_by_block_start` 命中时创建 heading；当 outline 阶段将锚点写在 **image/table** 块（`anchor_enricher` 在已有 `block_index` 时不会重算）时，该分支被跳过。

**缺失 outline 示例**：

| node_id | title | 锚定块类型 |
|---------|-------|------------|
| n1 | 谈判报价函 | image |
| n135 | 售后响应三大保障，7*24小时保驾护航 | table |
| n136 | 专业售后团队，多渠道快速接入 | image |

> chunk / linkage 不受此影响（按 `char_start` 切片），但 **DocumentTreeNode 落库** 与 `linkage.document_tree_node_ids` 会不完整。

---

## 3. 功能需求

### R1 — document_tree 节点 ID 全局唯一（P0）

**需求**：`document_tree.json` 中所有 `node_id` MUST 唯一。

**实现要求**：

1. `tree/builder.py` 使用**单一单调递增**计数器生成 ID，例如 `t0001`、`t0002`…，禁止 heading 与 body 各用一套格式化序号。
2. 或改用 UUID / `t-{sort_order}` 等不会碰撞的策略；若保持 `t{nnnn}` 前缀，须在契约中固定宽度与算法。
3. 新增单元测试 `test_document_tree_node_ids_unique`，对合成 fixture 与餐补样例结构（可缩小）断言无重复。

**验收**：

```bash
python -m pytest tests/unit/test_document_tree.py -v
# 且对 zhongyin-canbu-v2 重跑 pipeline 后 duplicate node_id 数为 0
```

---

### R2 — 每个 outline 节点必有 document_tree heading（P0）

**需求**：对 `outline.json` 中每个节点 `node_id`，`document_tree.json` MUST 存在且仅存在**一个** `node_type=heading` 且 `outline_node_id` 等于该 ID 的节点。

**例外**：仅当 `outline.strategy == "flat_fallback"` **且** `len(outline.nodes) == 1` 时，可不要求独立 heading。

**实现要求**（**方案 A + B 均须实现**）：

**方案 B — anchor_enricher 前移锚点（前置）**

在 `enrich_outline_anchors` 中，当 outline 节点锚定在 `image`/`table` 块（含 outline 阶段已写入的 `block_index`）时：

1. 从当前锚点 block 起，向后搜索至**下一 outline 节点的 `block_start`**（最后一个节点搜至文档末）；
2. 取首个 `paragraph` 块，或 `_normalize_title` 与 `outline.title` 匹配的块；
3. 命中则更新 `anchor.block_index`、`block_start`、`char_start`、`char_end`；
4. 未命中则保留原锚点，交由方案 A 合成 heading。

**方案 A — tree 阶段兜底（后置）**

在 `build_document_tree` 遍历 `content.blocks.json` 结束后：

1. 对比 `outline.nodes` 与已生成 heading 的 `outline_node_id` 集合；
2. 对缺失节点**合成 heading 节点**（遍历阶段已建 heading 的节点**禁止重复合成**）：
   - `title` = outline.title
   - `level` = outline.level
   - `parent_id` 按 outline.parent_id 映射到已生成的 tree heading
   - `source_block_index` = outline.anchor.block_start（可为 image/table）
   - `sort_order`：按 `source_block_index` 插入，位于同 block 的 body 节点**之前**（标题在内容前）
3. 不重复创建 body 节点（image/table 块仍保留原 `node_type`）。

**重复 `block_start`**

多个 outline 节点可共享同一 `block_start`；每个 outline 仍各有一个独立 heading（`source_block_index` 可相同、`outline_node_id` 不同）。须在 `manifest.warnings` 写入 `outline_duplicate_anchor:{block_start}`。

**契约测试**：

```python
# tests/contract/test_document_tree_outline_coverage.py
assert len(heading_outline_ids) == len(outline.nodes)
assert heading_outline_ids == {n.node_id for n in outline.nodes}
```

---

### R3 — linkage 与 tree 一致性（P0）

**需求**：`linkage.json` MUST 为**每个** `outline.json` 节点生成一条 entry（`flat_fallback` 单节点例外见 R2）。每条 entry 的 `document_tree_node_ids` MUST 非空。

**实现要求**：

1. `linkage/builder.py` 重构为全覆盖：无对应 chunk 时 `chunk_ids=[]`，`primary_chunk_id=null`（或省略），但 `document_tree_node_ids` 仍指向 R2 heading。
2. 缺失 `document_tree_node_ids` 时写入 `manifest.warnings` 条目 `linkage_missing_tree_node:{outline_node_id}`。
3. **`chunks/index.json` 必写 `document_tree_node_id`**：`chunk` 阶段取 linkage 对该 outline 的主 heading `node_id`（`document_tree_node_ids[0]`）；与 linkage 不一致时写入 manifest warning `chunk_tree_node_mismatch:{chunk_id}`。

---

### R4 — blocks_v1 图片块消费契约（P1）

**需求**：提供与 `tender_knowledge` `content_blocks.blocks_v1` 对齐的导出方式。

**tk 期望**（图片块）：

```json
{"type": "image", "asset_id": "<uuid>", "alt": "可选"}
```

**doc_chunk 当前**：

```json
{"type": "image", "image_ref": "images/docx-img-001.jpeg"}
```

**实现要求**：

1. 扩展 `doc_chunk.convert.blocks_v1`：

```python
def blocks_to_v1_json(
    blocks: list[ChunkBlock],
    *,
    image_ref_to_asset_id: dict[str, str] | None = None,
) -> str:
    ...
```

2. **Canonical 输出（双字段并存）**：
   - 无映射：`{"type": "image", "image_ref": "images/..."}`
   - 有映射：`{"type": "image", "asset_id": "<uuid>", "image_ref": "images/..."}`（`image_ref` 保留作追溯）
   - 工作区 `chunk.blocks` JSON **不变**（仍用 `image_ref`）；仅 `blocks_to_v1_json` 转换层产出 `asset_id`。
3. 在 `workspace-schemas.md` 与集成规格中写明**推荐路径**：适配层注册 `images/manifest.json` 后注入 `image_ref_to_asset_id` 映射。
4. 单元测试：paragraph/table/image 三类块序列化后 tk `parse_content` 可解析（可在 tk 侧加可选跨仓契约，或在本仓 mock tk 解析逻辑）。

---

### R5 — enrich 候选类型元数据（P1）

**需求**：`enrich` 规则路径下，根据标题/正文关键词填充 `metadata.suggested_candidate_type` 与 `metadata.suggested_knowledge_type`。

> **现状**：`candidate_rules.yaml` 与 `suggest_candidate_types()` 已在 002 部分落地；003 补齐默认配置与直映射路径。

**实现要求**：

1. **扩展 `default_classification.yaml`**：增加通用 `chapter_taxonomies`，使 enrich 无 `--classification-config` 时也能产出 `chapter_taxonomy_hints` 并触发 `suggested_*`。
2. **关键词直映射**：`labels` 关键词规则命中 `knowledge_type` 时，**直接**写入 `suggested_candidate_type` / `suggested_knowledge_type`（不依赖 `chapter_taxonomy_hints` 中间层）。
3. **扩展 `candidate_rules.yaml`**（可与 tk `chapter_candidate_rules.yaml` 结构对齐）：支持 `ignore` 规则；命中时 `suggested_candidate_type: ignore`，`suggested_knowledge_type: null`。
4. `classify_chunk` 写入枚举：
   - `suggested_candidate_type`: `scheme` | `product` | `qualification` | `ignore`
   - `suggested_knowledge_type`: `scheme` | `product` | `qualification` | `null`（当 `ignore`）
5. 餐补样例重跑 enrich 后，技术方案类 chunk 应出现非空 `suggested_candidate_type`（抽样断言）。

---

### R6 — anchor 落在非段落块的回归测试（P0）

**需求**：固定 fixture 覆盖「目录标题对应图片/表格块」场景。

**fixture**（两个独立文件，契约测试各跑一遍）：

| 文件 | 构造 |
|------|------|
| `tests/fixtures/outline_anchor_on_image.docx` | 第 1 块为图片，TOC/目录条目「封面」指向该图 |
| `tests/fixtures/outline_anchor_on_table.docx` | table 首行文字作为 TOC 标题 |

**断言**（每个 fixture）：

- outline 节点 ≥ 2
- chunk 与 outline 对齐（沿用 `test_chunk_anchor_alignment`）
- document_tree heading 覆盖全部 outline 节点（R2）
- node_id 无重复（R1）

---

### R7 — 大文件回归门禁（P1）

**需求**：在 CI 或 `tests/integration` 中可选运行餐补样例（路径由环境变量 `DOC_CHUNK_CANBU_FIXTURE` 提供）；若未设置则 skip。

**断言**（最小集）：

- `duplicate node_id == 0`
- `len(outline) == len(linkage.entries)`（flat_fallback 单节点例外见 R2）
- 全部 linkage entry 的 `document_tree_node_ids` 非空
- `chunks` 主块数 / `len(outline)` ∈ [0.8, 1.2]

---

## 4. 非功能需求

| ID | 要求 |
|----|------|
| NF1 | R1–R3 修复后，餐补 E2E pipeline 耗时不超过基线 120%（见 §4.1） |
| NF2 | 所有新行为 additive；不破坏 `schema_version: 1.0` 既有字段 |
| NF3 | `python -m pytest tests/unit tests/contract -q` 全绿 |

### 4.1 NF1 — 性能基线度量规范

**测量对象**：餐补全流程集成测试（End-to-End Pipeline）的整体 **Wall Time**。

**基线确立**（003 改造前）：

1. 在 `main` 分支本地环境连续运行 3 次餐补全流程测试；
2. 取耗时**中位数**为绝对基线 `T_base`。

**验收断言**（003 完工后）：

1. 同等硬件及负载环境（如相同 Mac M2）下同样跑 3 次取中位数 `T_003`；
2. 断言：`T_003 <= 1.2 * T_base`。

**监控归档**：

- 耗时对比须随测试日志显式打印（含 `T_base`、`T_003`、比值）；
- 记录在 003 Pull Request 说明中。

---

## 5. 交付切片

```text
P0（阻断 tk 落库）
  R1  node_id 唯一
  R2  outline → tree heading 全覆盖（方案 A + B）
  R3  linkage 全覆盖 + document_tree_node_ids 非空
  R6  双 fixture（image + table）+ 契约测试

P1（减少适配层成本）
  R4  blocks_v1 图片契约 / image_ref 映射 API
  R5  suggested_candidate_type 规则（扩展默认配置 + 直映射 + ignore）
  R7  大文件可选回归

P2（可选）
  - 工作区 export DTO（单文件汇总 outline+tree+linkage 摘要）
```

### 5.1 Plan Sync — 实现计划同步规则

维护代码库可追溯性：在 **003 提交的 PR 中**，顺手修正 [`../plans/2026-06-15-doc-chunk-tk-integration-fixes.md`](../plans/2026-06-15-doc-chunk-tk-integration-fixes.md) 中的过时表述。

**标注形态**：在诸如 R5「新增 `candidate_rules.yaml`」等已部分完成的条目后，显式加上 `[Partially Completed in 002 / 003 Refactored]` 后缀；**不删历史**，但标明当前现状，避免维护者心智冲突。

---

## 6. 验收标准（特性完成定义）

1. 重跑餐补样例：`document_tree` **0** 个重复 `node_id`
2. `outline` 173 节点 → `document_tree` **173** 个 heading 含对应 `outline_node_id`
3. `len(linkage.entries) == len(outline.nodes)`，全部 `document_tree_node_ids` 非空
4. `chunks/index.json` 每条 heading 级 entry 的 `document_tree_node_id` 与 linkage 一致
5. `tests/contract/test_document_tree_outline_coverage.py` 通过（含 image + table 双 fixture）
6. `blocks_to_v1_json` 文档与单测更新（双字段并存契约）
7. enrich 后至少 1 个 chunk 的 `suggested_candidate_type` 非空（默认配置，无需 `--classification-config`）
8. NF1：`T_003 <= 1.2 * T_base`，PR 中记录耗时对比
9. README 文档索引包含本规格；plan 文档已 Plan Sync 标注

---

## 7. 与 tender_knowledge 的分工

| 项 | doc_chunk（本特性） | tender_knowledge |
|----|---------------------|------------------|
| node_id 唯一 | R1 | — |
| outline↔tree 完整 | R2–R3 | 消费 linkage |
| image_ref → asset_id | R4 提供映射 API / 文档 | 适配层注册 manifest |
| 候选类型 | R5 输出 suggested_* | 映射 taxonomy UUID、过滤 ignore |
| DB 落库 | — | `doc_chunk_import_service` |

---

## 8. 参考

| 文档 | 路径 |
|------|------|
| 002 集成需求（主体） | [`2026-06-15-doc-chunk-tender-knowledge-integration.md`](./2026-06-15-doc-chunk-tender-knowledge-integration.md) |
| 002 实现计划 | [`../plans/2026-06-15-doc-chunk-tender-knowledge-integration.md`](../plans/2026-06-15-doc-chunk-tender-knowledge-integration.md) |
| tree 实现 | `src/doc_chunk/tree/builder.py` |
| linkage 实现 | `src/doc_chunk/linkage/builder.py` |
| tk blocks_v1 | `tender_knowledge/backend/src/services/content_blocks.py` |

---

## 9. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-06-15 | 集成复核后的修复需求（003） |
| 1.1 | 2026-06-15 | Clarifications 定稿（R2 A+B、linkage 全覆盖、NF1 度量、Plan Sync 等 12 项） |
