# 目录树「X、」大章识别优化需求

**日期**: 2026-07-01  
**来源**: tender_knowledge 知识录入 tree API 目录乱序问题  
**状态**: 已实现（`promote_headings` 扩展）

## 背景

投标文档常见两种章节标记并存：

- Word「标题 1」样式：如 `# 一、企业简介及资质`
- 普通段落：`二、百福得服务方案介绍`（未套标题样式）

`heading_heuristic` 只扫描 markdown `#` 标题，导致 outline 仅 1 个 L1 根节点，所有 1.x / 2.x / 3.x 小节被错误挂到「一、」下。

## outline_refine 为何不能作为主方案

| 问题 | 说明 |
|------|------|
| 依赖 LLM | 需配置 API Key，解析失败/超时影响整条 pipeline |
| 需显式 instruction | `skip_refine=False` 且 `refine_instruction` 非空才执行 |
| 无法补全缺失节点 | refine 基于已有 outline 节点做 merge/reparent；「二、三、四、」未进入 outline 时 LLM 需新建节点并维护 mapping，不稳定 |
| 非确定性 | 同类文档多次解析结果可能不一致 |

**结论**：`outline_refine` 适合人工指令微调目录，不适合作为知识录入默认路径的层级修复手段。

## 实现方案（已完成）

在 `extract/promote_headings.py` 扩展 `parse_content_heading_line`：

- 识别 `^[一二三四五六七八九十百零]+、\s*\S` 格式（如 `二、百福得服务方案介绍`）
- 在 `promote_headings="auto"` 时提升为 L1 markdown 标题
- `run_pipeline` 新增 `promote_headings` 参数并透传至 `extract_file`

tender_knowledge 默认：

- `doc_chunk_promote_headings=auto`（确定性修复）
- `doc_chunk_skip_refine=True`（保留可选 LLM refine，失败时 fallback）

## 验收标准

1. 含「一、」「二、」混排（部分无 Word 标题样式）的 docx，outline 根节点数 ≥ 2
2. `2.1` 等小节的 `parent_id` 指向对应「二、」大章，而非「一、」
3. tree API 同级节点按 `sort_order` 排列（非标题数字前缀）

## 后续可选增强

- `outline/builder.py`：当 `heading_heuristic` 检测到「单 L1 + 大量 L2 跨章编号」时发出 warning 或 fallback 到 `content_heuristic`
- `outline_refine` prompt 增加「从 content.md 补全 X、大章」示例（仍仅作可选人工 refine）
