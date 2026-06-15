# CLI Contract: doc-chunk

**Package**: `doc_chunk`  
**Entry point**: `doc-chunk` (typer)  
**Date**: 2026-06-15

## Global Options

| Option | Short | Description |
|--------|-------|-------------|
| `--verbose` | `-v` | 启用 DEBUG 日志 |
| `--config` | `-c` | 配置文件路径（YAML） |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | 成功 |
| 1 | 失败 |
| 2 | 部分成功（批量存在失败项） |
| 3 | 参数错误 |
| 4 | 不支持格式 |

---

## `doc-chunk extract`

提取文档到工作区。

```bash
doc-chunk extract <INPUT> --output <DIR> [--overwrite]
```

| Arg/Option | Required | Description |
|------------|----------|-------------|
| INPUT | yes | 文件或目录 |
| `--output` / `-o` | yes | 工作区根目录 |
| `--overwrite` | no | 覆盖已存在工作区 |

**Output**: stdout 打印 manifest 路径；stderr 警告。

**Batch**: INPUT 为目录时，逐文件创建 `<output>/<stem>/` 子工作区。

---

## `doc-chunk outline`

从已提取工作区生成目录树。

```bash
doc-chunk outline <WORKSPACE>
```

**Precondition**: `content.md` 存在。

**Output**: `<workspace>/outline.json`

---

## `doc-chunk refine`

LLM 优化目录树（单轮）。

```bash
doc-chunk refine <WORKSPACE> --instruction "<TEXT>" [--lenient]
```

| Option | Description |
|--------|-------------|
| `--instruction` / `-i` | 自然语言指令（必填） |
| `--lenient` | 宽松校验模式 |

**Precondition**: `outline.json` 存在；LLM 已配置。

**Output**: stdout JSON 预览（摘要，非完整树文件）

---

## `doc-chunk refine-accept`

确认并落盘优化目录树。

```bash
doc-chunk refine-accept <WORKSPACE>
```

**Output**: 写入 `outline_refined.json`, `outline_mapping.json`, `outline_refine_summary.md`

---

## `doc-chunk refine-discard`

放弃当前 refine session。

```bash
doc-chunk refine-discard <WORKSPACE>
```

---

## `doc-chunk refine-reset`

清除已 accept 的优化产物并开启新 session。

```bash
doc-chunk refine-reset <WORKSPACE> [--force]
```

---

## `doc-chunk chunk`

按目录树分块。

```bash
doc-chunk chunk <WORKSPACE> [--max-tokens 20000] [--use-original]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--max-tokens` | 20000 | 章节内续切上限 |
| `--use-original` | false | 强制使用 outline.json |

**Precondition**: `content.md` + (`outline.json` 或 `outline_refined.json`)

**Output**: `chunks/` + `chunks/index.json`

---

## `doc-chunk enrich`

块元数据增强（描述 + 分类）。

```bash
doc-chunk enrich <WORKSPACE> [--no-llm] [--classification-config PATH]
```

| Option | Description |
|--------|-------------|
| `--no-llm` | 仅规则分类，跳过描述 |
| `--classification-config` | 自定义 classification.yaml |

---

## `doc-chunk pipeline`

端到端流水线。

```bash
doc-chunk pipeline <INPUT> --output <DIR> \
  [--skip-refine] [--skip-enrich] [--refine-instruction "<TEXT>"] \
  [--overwrite] [--max-tokens 20000]
```

**Stages**: extract → outline → [refine + accept if instruction] → chunk → [enrich]

**Note**: 提供 `--refine-instruction` 时自动执行单轮 refine + accept；多轮需交互式调用 `refine` 子命令。

---

## Environment Variables

| Variable | Used by | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | refine, enrich | LLM API 密钥 |
| `OPENAI_API_BASE` | refine, enrich | API 基址（可选） |
| `DOC_CHUNK_LLM_MODEL` | refine, enrich | 模型名，默认 `gpt-4o-mini` |

---

## Stdout JSON Preview (refine)

```json
{
  "preview": {
    "node_count_before": 42,
    "node_count_after": 35,
    "change_summary": "合并了 3 组资质章节",
    "warnings": [],
    "title_diff": ["- 一、资格文件", "- 二、商务文件", "+ 资格与商务文件"]
  },
  "validation": {
    "passed": true,
    "errors": []
  }
}
```
