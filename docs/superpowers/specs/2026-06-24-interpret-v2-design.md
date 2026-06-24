# 设计规格：tender_insights interpret v2

**版本**: 1.0  
**日期**: 2026-06-24  
**状态**: 已批准  
**Feature ID**: `006-interpret-v2`  
**前置**: `005-tender-insights-skills`（v1 interpret）

---

## 1. 概述

重构 `tender_insights.interpret` 模块，实现：

1. **明细 + 概要** — `interpretation.json` 同时包含逐条明细与维度级概要
2. **全文覆盖提取** — 取消关键词路由，按逻辑完整分段覆盖全部正文
3. **目录格式** — 聚焦目录/文件组成，产出 `directory_outline` 供下游目录生成
4. **图片 OCR** — 默认 `qwen-vl-ocr`，hash 缓存，logo 跳过，大图压缩

**硬约束：不修改 `doc_chunk` 任何代码**；仅读取工作区产物，所有新逻辑在 `tender_insights` 内。

**范围外：** `legal`、`template` 模块本次不优化。

---

## 2. 已确认决策

| 决策点 | 选择 |
|--------|------|
| 包边界 | 只改 `tender_insights`；`doc_chunk` 只读 |
| v1 迁移 | **直接替换** interpret 主流程，移除 routing gate |
| 分段策略 | 优先复用 `chunks/index.json`，tender_insights 内 merge/split 至 2k–12k tokens |
| LLM 调用 | 每 segment **1 次**，一次返回四类明细；固定 system prompt 利于 cache |
| 概要生成 | 明细合并后 **单独 1 次** LLM，输入为明细摘要（非全文） |
| OCR 范围 | 仅 `content.md` 中 `![](...)` 引用的图片 |
| OCR 去重 | SHA256 hash 缓存于 `interpret/ocr_cache.json` |
| Logo 跳过 | 文件 ≤10KB **且**（宽或高 <128px） |
| 大图预处理 | 长边压缩至 ≤1500px 再 OCR |
| OCR 模型 | 默认 `qwen-vl-ocr` |
| 原文锚点 | 锚点回填针对 `interpret/source_content.md`（OCR enrichment 视图） |
| `content.md` | **不修改**（doc_chunk 产物保持原样） |

---

## 3. 架构

### 3.1 流水线

```text
resolve_workspace(path)
    ↓
interpret_workspace(workspace, client):
  1. ocr_enrich(workspace)           → interpret/source_content.md + interpret/ocr_cache.json
  2. plan_segments(source, config)  → Segment[]（全文覆盖）
  3. for seg in segments:
       LLM once → InterpretationLLMResponse（四类明细）
  4. merge + dedupe + anchor_backfill(source_content)
  5. build_overview(client, merged)  → InterpretationOverview
  6. build_directory_outline(merged) → DirectoryOutline
  7. write interpretation.json (schema 1.1)
```

### 3.2 新增模块

| 路径 | 职责 |
|------|------|
| `tender_insights/common/ocr/client.py` | DashScope 兼容 OCR API（qwen-vl-ocr） |
| `tender_insights/common/ocr/enricher.py` | hash 缓存、logo 跳过、压缩、写 source_content |
| `tender_insights/common/ocr/models.py` | OcrCacheFile、OcrCacheEntry |
| `tender_insights/common/content_source.py` | `InterpretSource` 数据类 + `prepare_interpret_source` |
| `tender_insights/common/segment_planner.py` | 读 chunks / fallback 自切；merge/split |
| `tender_insights/interpret/overview.py` | 概要 LLM 生成 |
| `tender_insights/interpret/directory_outline.py` | 从 directory_requirements 规范化目录树 |

### 3.3 废弃（interpret 路径）

- `SectionRouter` + `interpret/routing.yaml` 作为覆盖 gate
- `prompts.build_user_prompt` 中 `markdown[:12000]` 硬截断
- `node_char_range` 驱动的章节切片作为主流程

保留 `section_slice.substitute_tables_for_llm` 供 segment 正文增强。

---

## 4. 数据模型

### 4.1 `interpretation.json` schema 1.1

```json
{
  "schema_version": "1.1",
  "source_workspace": "/abs/path/to/workspace",
  "analyzed_at": "2026-06-24T12:00:00+00:00",
  "segment_count": 12,
  "ocr_image_count": 3,

  "overview": {
    "summary": "整份招标文件解读概要（200–800字）",
    "disqualification_summary": "废标项总体说明",
    "scoring_summary": "评分办法总体说明（含总分结构）",
    "bid_risk_summary": "投标风险总体说明",
    "directory_summary": "投标文件组成/目录要求总体说明"
  },

  "disqualification_items": [],
  "scoring_items": [],
  "bid_risk_items": [],

  "directory_requirements": [{
    "id": "dr-001",
    "title": "投标文件组成",
    "required_sections": ["投标函", "..."],
    "mandatory": true,
    "structure": [{
      "order": 1,
      "number": "一",
      "title": "投标函",
      "mandatory": true,
      "children": []
    }],
    "source_excerpt": "...",
    "section_path": ["...", "投标文件格式"],
    "char_start": 123,
    "char_end": 456,
    "confidence": 0.9
  }],

  "directory_outline": {
    "confidence": 0.85,
    "nodes": [{
      "id": "dir-1",
      "title": "投标函",
      "level": 1,
      "order": 1,
      "mandatory": true,
      "number": "一"
    }]
  }
}
```

### 4.2 Segment（内部）

```python
@dataclass
class Segment:
    segment_id: str           # seg-001
    section_path: list[str]
    markdown: str
    char_start: int
    char_end: int
    token_estimate: int
```

### 4.3 OCR 缓存 `interpret/ocr_cache.json`

```json
{
  "schema_version": "1.0",
  "entries": {
    "<sha256>": {
      "image_ref": "images/docx-img-001.png",
      "text": "OCR 文本",
      "status": "success",
      "model": "qwen-vl-ocr",
      "skipped_reason": null
    }
  }
}
```

`skipped_reason` 可选值：`logo`、`cached`、`failed`。

---

## 5. 分段策略

### 5.1 输入来源

1. **优先**：读取 `chunks/index.json`，加载各 chunk 的 `markdown`、`section_path`、`token_estimate`
2. **Fallback**：读取 `content.md` + `outline.json`，按 Markdown 标题切 section（逻辑写在 `segment_planner.py`，不调用 doc_chunk API）

### 5.2 Merge / Split 规则

| 规则 | 阈值 |
|------|------|
| 合并 | 相邻段 `< 2000` tokens 且 `section_path` 前 2 级相同 |
| 拆分 | 段 `> 12000` tokens，按行拆分；硬上限 15000 |
| 表格 | 来自 `content.blocks.json` 的 table 块不从中途切断 |
| 空段 | 纯空白跳过 |

分段前对每段 markdown 调用 `substitute_tables_for_llm`。

### 5.3 Token 估算

复用 `doc_chunk.chunk.tokenizer.estimate_tokens`（只读 import，不改 doc_chunk）。

---

## 6. LLM 调用设计

### 6.1 Segment 提取（每段 1 次）

**System（固定，利于 prefix cache）：**

```
你是招标文件解读专家。从给定正文片段中提取结构化信息。
只输出 JSON，字段：
- disqualification_items: 废标项（含 trigger_condition）
- scoring_items: 得分项（含 max_score, weight, criteria）
- bid_risk_items: 投标视角风险（severity: high|medium|low, risk_category）
- directory_requirements: 目录/文件组成（required_sections, mandatory, structure 树形可选）
每条必须有 source_excerpt、section_path、confidence。
若无某类内容，返回空数组。
```

**User（每段不同）：**

```
segment_id: seg-003
section_path: 投标人须知 > 废标条款

正文:
{segment.markdown}
```

### 6.2 Overview 生成（全文 1 次）

输入：合并去重后的四类明细（仅 title + summary + max_score/weight 等关键字段 JSON），要求输出 `overview` 五个 summary 字段 + 顶层 `summary`。

---

## 7. OCR

### 7.1 流程

1. 解析 `content.md` 中 `![...](images/xxx)` 引用（唯一路径集合）
2. 对每个文件计算 SHA256
3. 查 `interpret/ocr_cache.json` → 命中则跳过 API
4. 读取图片尺寸与文件大小 → logo 规则跳过（≤10KB 且宽或高 <128px）
5. Pillow 长边 >1500px → 等比缩放
6. 调用 `qwen-vl-ocr`（OpenAI 兼容 multimodal messages）
7. 写入 cache；在 `source_content.md` 中于图片行后插入 OCR 文本块：

```markdown
![docx-img-001](images/docx-img-001.png)

<!-- ocr:sha256:abc123... -->
（OCR 文本）
<!-- /ocr -->
```

### 7.2 配置

| 环境变量 | 默认 |
|----------|------|
| `OCR_ENABLED` | `true` |
| `OCR_MODEL` | `qwen-vl-ocr` |
| `SEGMENT_MIN_TOKENS` | `2000` |
| `SEGMENT_MAX_TOKENS` | `12000` |
| `OCR_LOGO_MAX_BYTES` | `10240` |
| `OCR_LOGO_MAX_PX` | `128` |
| `OCR_MAX_LONG_EDGE` | `1500` |

沿用 `LLM_API_KEY`、`LLM_BASE_URL`（DashScope compatible endpoint）。

### 7.3 依赖

新增 `Pillow>=10.0.0` 至 `pyproject.toml` project dependencies。

---

## 8. 目录格式（directory_outline）

### 8.1 目标

为下游「投标目录自动生成」提供标准树形输入。

### 8.2 构建逻辑

1. LLM 在 segment 提取时尽量填充 `directory_requirements[].structure`
2. `build_directory_outline` 合并所有 structure，去重，生成扁平 `nodes` 列表（含 level/order/mandatory/number）
3. 若无 structure，从 `required_sections` 扁平化为 level=1 节点
4. `confidence` = 有 structure 的条目占比或 LLM 均值

---

## 9. 合并与锚点

### 9.1 去重

跨 segment 按 `(kind, normalized_title)` 去重；同 title 保留更高 `confidence` 或更长 `source_excerpt`。

### 9.2 锚点

`backfill_char_range` 针对 `interpret/source_content.md`；失败时 `char_start`/`char_end` 为 null，保留 `section_path`。

---

## 10. manifest 扩展

`write_json_artifact` 追加 stage：

- `interpret_ocr` → `interpret/ocr_cache.json`（OCR 完成后）
- `interpret` → `interpretation.json`（不变）

---

## 11. 测试策略

| 层级 | 范围 |
|------|------|
| 单元 | segment_planner merge/split；OCR hash 缓存、logo 跳过、压缩；directory_outline；overview schema |
| 契约 | `interpretation.json` schema 1.1 必填字段 |
| 集成 | sample docx workspace → interpret → `overview` 非空、`segment_count >= 1` |
| 回归 | 更新 `test_pipeline_interpret.py`；移除 routing 依赖断言 |

---

## 12. 非目标

- 修改 `doc_chunk` 任何代码
- `legal` / `template` 模块优化
- zip 附件包模版
- 多文件工作区合并分析
- Web UI 改造

---

## 13. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 全文 segment 数量多 → LLM 成本高 | merge 小段；OCR 仅引用图；hash 缓存 |
| OCR API 不稳定 | cache + status=failed 仍继续 interpret |
| schema 1.0 消费者 | 新增字段可选；`schema_version` 区分 |
| 无 chunks 的工作区 | fallback 自切 section |
