# Changelog

## [0.2.0] - 2026-07-02

### Changed (Breaking)

- **`outline.json` `anchor.char_start` 语义变更**：现与 viewer `GET /sections/{node_id}` 返回的 `char_start` 完全一致，跳过文首内嵌目录（`标题\t页码`）行。已解析文档需重新跑 doc-chunk 流水线；不自动回写历史 `outline.json`。
- 新增共享模块 `doc_chunk.locate.heading_starts`，viewer 与 `anchor_enricher` 共用标题定位逻辑。

### Fixed

- 修复 TOC 标书场景下 outline anchor 落在目录区、导致 tender_knowledge 章节预览 `content_md` 几乎为空的问题。
