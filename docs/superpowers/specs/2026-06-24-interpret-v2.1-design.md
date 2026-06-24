# 设计规格：tender_insights interpret v2.1

**版本**: 1.0  
**日期**: 2026-06-24  
**状态**: 已批准（brainstorming）  
**Feature ID**: `006-interpret-v2.1`  
**前置**: `006-interpret-v2`（schema 1.1，全文分段提取）

---

## 1. 概述

在 interpret v2 基础上改进提取质量，解决三类实际问题：

1. **得分项为空** — 「第二章 响应人须知」等章节含大量评分内容却未进入 `scoring_items`
2. **目录粒度错误** — 应提取完整目录框架，而非零散小点；无明确章节时应产出概要 + 推断清单
3. **完整性不足** — 分块提取后废标/评分/风险应有列表 + 概要，评分须带细则

**硬约束：**

- 不增加 LLM 调用次数（每 segment 仍 1 次提取 + 全文 1 次 overview）
- 不修改 `doc_chunk` 任何代码
- 在 `tender_insights` 包内实现

---

## 2. 已确认决策

| 决策点 | 选择 |
|--------|------|
| 评分粒度 | **两层树** — 大类为 `ScoringItem` 父项，细则为 `children[]` |
| 目录（无明确章节） | **概要 + 推断清单** — `overview.directory_summary` 为主，合并为 `inferred: true` 的 `directory_requirements` |
| 完整性策略 | **强化 Prompt** — 不增加二次扫描 LLM |
| 实现路径 | **方案 2** — Schema 1.2 + System Prompt 重写 + 按 `section_path` 注入分段附录 |

---

## 3. 问题根因（v2）

| 现象 | 根因 |
|------|------|
| 得分项为空 | Prompt 未说明响应人须知内嵌评分须提取；四类同段竞争；「若无则 []」导致跳过 |
| 目录零散 | Prompt 未区分「完整 structure 树」vs 扁平列表；`build_directory_outline` 只取顶层节点 |
| 细则缺失 | `criteria` 仅定义为摘要，无 `children` 结构 |
| 概要空洞 | `scoring_summary` 依赖 `scoring_items` 明细；明细为空则概要无依据 |

---

## 4. Schema 1.2

`schema_version` 升为 `"1.2"`。相对 1.1 **增量扩展**，旧字段保留，新字段有默认值，1.1 消费者仍可读。

### 4.1 新增 `ScoringCriterionNode`

```json
{
  "id": "sc-001-01",
  "title": "方案完整性",
  "max_score": 10.0,
  "score_range": "0-10",
  "criteria": "细则全文：含评分档位、加分/扣分条件",
  "source_excerpt": "原文摘录"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 子项 ID，如 `sc-001-01` |
| `title` | string | 细则名称 |
| `max_score` | float \| null | 该项满分 |
| `score_range` | string \| null | 分值区间描述，如 `0-10`、`每项2分` |
| `criteria` | string | **评分细则全文**（可操作细节，非笼统摘要） |
| `source_excerpt` | string | 原文摘录 |

### 4.2 `ScoringItem` 扩展

在 1.1 字段基础上新增：

```json
{
  "id": "sc-001",
  "title": "技术部分",
  "summary": "技术评分总体说明",
  "max_score": 40.0,
  "weight": "40%",
  "criteria": "大类层面评分原则（细则放 children）",
  "children": [ "/* ScoringCriterionNode[] */" ],
  "source_excerpt": "...",
  "section_path": ["第二章 响应人须知", "评审办法"],
  "char_start": null,
  "char_end": null,
  "confidence": 0.9
}
```

**规则：**

- 有分值表 → 按表结构建父项 + `children[]` 填满细则
- 仅有大类、无子项细则 → `children` 可为 `[]`，`criteria` 写尽已知信息
- 父项 `max_score` 宜等于子项分值之和；无法确定时为 `null`

### 4.3 `DirectoryRequirement` 扩展

新增字段：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `inferred` | bool | `false` | `true` 表示从全文推断，非招标原文明确目录章节 |

**行为：**

| `inferred` | 场景 | 产出 |
|------------|------|------|
| `false` | 有「投标文件组成 / 格式 / 目录」等明确章节 | 完整 `structure` 树（含层级、序号、mandatory）；有 `structure` 时 `required_sections` 可为空 |
| `true` | 无明确目录章节 | 合并各段零散材料要求为一棵推断树；同时充实 `overview.directory_summary` |

### 4.4 `overview` — 不变

仍为五个 summary 字段。`scoring_summary` 须反映总分结构、各大类要点及关键细则。

### 4.5 完整顶层示例（节选）

```json
{
  "schema_version": "1.2",
  "overview": {
    "summary": "...",
    "disqualification_summary": "...",
    "scoring_summary": "总分100分：技术40分（含方案完整性10分…）、商务30分…",
    "bid_risk_summary": "...",
    "directory_summary": "..."
  },
  "scoring_items": [
    {
      "id": "sc-001",
      "title": "技术部分",
      "summary": "技术评分",
      "max_score": 40.0,
      "weight": "40%",
      "criteria": "技术方案综合评价",
      "children": [
        {
          "id": "sc-001-01",
          "title": "方案完整性",
          "max_score": 10.0,
          "score_range": "0-10",
          "criteria": "方案覆盖全部招标要求得10分，每缺一项扣2分",
          "source_excerpt": "..."
        }
      ],
      "source_excerpt": "...",
      "section_path": ["第二章 响应人须知"],
      "confidence": 0.9
    }
  ],
  "directory_requirements": [
    {
      "id": "dr-001",
      "title": "投标文件组成",
      "inferred": false,
      "required_sections": [],
      "structure": [
        {
          "order": 1,
          "number": "一",
          "title": "投标函",
          "mandatory": true,
          "children": []
        }
      ],
      "mandatory": true,
      "source_excerpt": "...",
      "section_path": ["第六章 投标文件格式"],
      "confidence": 0.9
    }
  ]
}
```

---

## 5. Prompt 策略

### 5.1 System Prompt 分类边界

| 类型 | 提取范围 | 勿归入 |
|------|----------|--------|
| `scoring_items` | 评审办法、评分标准、分值表、加扣分项；**含响应人/投标人须知内嵌评分** | 纯程序性须知 |
| `disqualification_items` | 废标、无效投标、否决投标的触发条件 | 仅扣分不废标 |
| `bid_risk_items` | 资格、符合性、实质性响应等投标执行风险 | 有明确分值的评分细则 |
| `directory_requirements` | 投标文件组成、格式、目录章节 | 评分表、废标条款 |

**评分：** 有表则父项 + `children`；细则 `criteria` 含档位与加扣分规则；同段有评分内容时**禁止**返回空 `scoring_items`。

**目录：** 明确章节 → `inferred: false` + 完整 `structure` 树，禁止拆成零散 `required_sections`；无明确章节 → 本段不强行造目录条目。

### 5.2 分段附录（按 `section_path` 关键词）

在 `build_segment_prompt` 中，对 `section_path` 做子串匹配（不区分大小写），命中则追加 user message 附录：

| 关键词（任一命中） | 附录 |
|--------------------|------|
| 响应人须知、投标人须知、供应商须知 | 本段常含评审/评分办法，请重点提取 `scoring_items`（含 `children` 细则） |
| 评标、评审、评分、分值、得分 | 本段为评分核心章节，须提取完整 `scoring_items` 树 |
| 废标、无效投标、否决 | 本段重点提取 `disqualification_items` |
| 投标文件组成、文件格式、目录、装订 | 本段重点提取 `directory_requirements`（`inferred=false`，完整 `structure` 树） |

多关键词可同时命中，附录合并；无命中不加附录。

### 5.3 Overview Prompt

输入合并明细时：

- `scoring_items` 含 `children` 的 `title`、`criteria` 摘要
- `directory_requirements` 含 `inferred` 字段
- 要求 `scoring_summary` 写清总分结构、大类要点、关键细则

---

## 6. 流水线

```
resolve_workspace
  → ocr_enrich → plan_segments
  → for seg: LLM once (schema 1.2 四类明细 + 分段附录)
  → merge_scoring_items (父项合并 + children union)
  → dedupe disqualification / bid_risk / directory
  → normalize_directory_requirements (零散 → inferred 树)
  → anchor_backfill
  → build_overview (1 LLM)
  → build_directory_outline (递归 structure)
  → write interpretation.json
```

LLM 调用次数与 v2 相同：**N segments + 1 overview**。

### 6.1 评分合并 `merge_scoring_items`

- 父项去重键：`(normalized_title, max_score)`
- 同父项合并：`children` 按 `normalized_title` union，保留更长 `criteria` / `source_excerpt`
- 跨段同名大类（如「技术部分」）合并为一个父项
- 输出按文档出现顺序排列

### 6.2 目录规范化 `normalize_directory_requirements`

1. 若存在 `inferred=false` 且 `structure` 非空 → 保留，作为权威目录
2. 否则将各段零散 `required_sections` / 空 `structure` 条目合并为**一条** `inferred: true`：
   - `title`: `"推断投标文件组成"`
   - `structure`: 每项升为一级 `DirectoryStructureNode`
   - `confidence`: 最高 0.65
3. `overview.directory_summary` 由 overview LLM 归纳（含推断说明）

### 6.3 `build_directory_outline` 增强

- 递归展开 `structure`（含 `children`），生成带 `level` / `order` 的扁平 `nodes[]`
- 优先 `inferred=false` 的来源
- `inferred=true` 时 `confidence` 0.5–0.6
- 前序遍历赋值 `order`

### 6.4 锚点回填

- 父项 `ScoringItem`：`source_excerpt` 回填 `char_start` / `char_end`
- 子项：各自 `source_excerpt` 独立回填；失败时可为 `null`

---

## 7. 模块变更

| 路径 | 变更 |
|------|------|
| `interpret/models.py` | `ScoringCriterionNode`；`ScoringItem.children`；`DirectoryRequirement.inferred`；`schema_version` 1.2 |
| `interpret/prompts.py` | 重写 `SYSTEM_PROMPT`；`build_segment_prompt` 加分段附录；更新 overview 相关 prompt |
| `interpret/merger.py` | `merge_scoring_items`；目录相关去重调整 |
| `interpret/directory_outline.py` | 递归展开 `structure` |
| `interpret/extractor.py` | 调用新 merge/normalize；schema 1.2 写入 |
| `interpret/overview.py` | payload 含 `children`、`inferred` |
| `.cursor/skills/tender-interpret/SKILL.md` | 文档更新至 schema 1.2 |
| `tests/` | 单元/契约/集成测试更新 |

**不新增 LLM 调用模块。**

---

## 8. 测试策略

| 层级 | 范围 |
|------|------|
| 单元 | `merge_scoring_items` 父子合并；`normalize_directory_requirements` inferred 合并；`build_directory_outline` 递归；分段附录关键词匹配 |
| 契约 | schema 1.2 必填/默认字段；1.1 向后兼容（空 `children`、`inferred=false`） |
| 集成 | FakeLLM 返回带 `children` 的 scoring；断言 section_path 含「响应人须知」时附录注入 |

---

## 9. 非目标

- 额外 LLM 二次扫描或完整性校验调用
- 修改 `doc_chunk`
- `legal` / `template` 模块
- Viewer UI 大改（可后续跟进展示 `children` 树）

---

## 10. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 复杂评分表一次输出树不稳定 | 分段附录 + 合并 union children；重试 JSON 校验 |
| 推断目录准确度有限 | `inferred: true` + 较低 confidence；概要中说明推断性质 |
| Prompt 变长增加 token | 附录仅命中时追加；system prompt 保持精炼 |
| 1.1 消费者不识别 `children` | 默认 `[]`；父项 `criteria` 仍保留大类信息 |
