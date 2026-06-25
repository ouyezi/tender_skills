---
name: tender-gen-catalog
description: >-
  Generate bid response catalog/outline from interpretation results. Use when
  the user asks for 投标目录、目录生成、gen-catalog, or bid_outline.json.
---

# tender-gen-catalog

在招标文件**已解读**后，生成投标响应目录方案（树 + 概要 + 撰写规范 + 废标/评分/模板引用）。

## 前置

工作区需有 `interpretation.json`；建议另有 `tender_brief.json`、`templates/index.json`。

```bash
.venv/bin/tender-insights interpret ./output/my-bid
.venv/bin/tender-insights brief ./output/my-bid
.venv/bin/tender-insights template ./output/my-bid
```

## 命令

```bash
# 一次性
.venv/bin/tender-insights gen-catalog ./output/my-bid

# 按步
.venv/bin/tender-insights gen-catalog ./output/my-bid --step --once
.venv/bin/tender-insights gen-catalog ./output/my-bid --continue
.venv/bin/tender-insights gen-catalog ./output/my-bid --accept
```

## 产物

- `bid_outline.draft.json` — 预览
- `bid_outline.json` — accept 后正式产物
- `gen_catalog/session.json` — 按步状态

## Viewer

`/gen-catalog?session_id=<解读会话ID>`
