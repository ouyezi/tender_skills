# Changelog

## Unreleased

### Fixed

- DOCX TOC 粘连页码 / toc 样式场景下，outline anchor 不再落在文首目录区：书签优先定位 + `body_start` 围栏 + 扩展 `is_toc_entry_line`；提取阶段 toc 样式不再写成 Markdown 标题。已解析文档需重跑流水线。

## [0.3.0] - 2026-07-06

### Added

- 新增 `agent_platform` 包：`AgentClient.invoke(call_type, input)` 统一大模型 / OCR 调用入口，支持 `AGENT_INVOKE_MODE=local|platform`（默认 `local`）。
- local 模式：16 个 call_type 均有 `handlers/{call_type}.py`（含 `ocr_image_recognize`）。
- platform 模式：`PlatformBackend` 调用 df-agent-os `POST /v1/apps/invoke`（`appName` = call_type）。
- 共享 helper：`invoke_json_model` / `invoke_text`（盲重试）；insights 侧 `extract_json_via_agent` 写 `llm_calls.jsonl`。
- 环境变量：`AGENT_INVOKE_MODE`、`AGENT_PLATFORM_BASE_URL`（见 `.env.example`）。

### Changed

- 全部业务 LLM/OCR 调用点经 `AgentClient` 接入（outline_refine 试点 + Batch A–E：metadata / OCR / interpret / brief / gen_catalog / template / legal）。
- 重试语义改为**同 input 盲重试**，不再把校验错误追加进 messages。
- 规格文档：`docs/agent_requirements.md` 同步为已落地架构。

### Docs

- 设计：`docs/superpowers/specs/2026-07-06-agent-platform-invoke-design.md`、`…-migrate-remaining-design.md`（Batch A–E 验收勾选完成）。

## [0.2.0] - 2026-07-02

### Changed (Breaking)

- **`outline.json` `anchor.char_start` 语义变更**：现与 viewer `GET /sections/{node_id}` 返回的 `char_start` 完全一致，跳过文首内嵌目录（`标题\t页码`）行。已解析文档需重新跑 doc-chunk 流水线；不自动回写历史 `outline.json`。
- 新增共享模块 `doc_chunk.locate.heading_starts`，viewer 与 `anchor_enricher` 共用标题定位逻辑。

### Fixed

- 修复 TOC 标书场景下 outline anchor 落在目录区、导致 tender_knowledge 章节预览 `content_md` 几乎为空的问题。
