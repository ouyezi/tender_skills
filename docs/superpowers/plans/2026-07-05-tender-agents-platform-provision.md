# Tender Skills 智能体平台 Provision 实现计划

> **状态：已完成（2026-07-05）** — `scripts/provision_agent.py` + `scripts/agents/*.json` 已落地。下列 checkbox 为历史实施步骤。
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 `scripts/provision_agent.py` + 16 个 JSON 配置，将 tender_skills 全部 call_type 注册到 df-agent-os-python（Agent + Application），并通过 `/v1/apps/invoke` 验证返回格式。

**Architecture:** 单文件 Python 脚本（stdlib `urllib` + 项目已有 `pydantic`），读取 `scripts/agents/*.json`，按 enName 幂等 upsert 模型/Agent/Application，最后用配置内 fixture 调生产 invoke 并校验 `structuredOutput`/`output` 格式。Prompt 优先从 `promptFile` 读取，Python 模块内 prompt 用 `promptText` 内联。

**Tech Stack:** Python 3.11+、Pydantic v2、urllib（HTTP）、df-agent-os-python REST API（`:8000`）

**设计文档:** `docs/superpowers/specs/2026-07-05-tender-agents-platform-provision-design.md`

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `scripts/provision_agent.py` | 唯一脚本：CLI、HTTP 客户端、upsert、verify |
| `scripts/agents/*.json` | 16 个 call_type 配置（prompt/schema/fixture） |
| `tests/scripts/test_provision_verify.py` | 纯函数单元测试（schema 校验，无网络） |

---

### Task 1: 输出格式校验单元测试

**Files:**
- Create: `tests/scripts/test_provision_verify.py`
- Create: `tests/scripts/conftest.py`（空文件或 `pytest` 路径 hook，可选）

- [ ] **Step 1: 写失败测试**

```python
# tests/scripts/test_provision_verify.py
from __future__ import annotations

import pytest

from scripts.provision_agent import (
    ValidationError,
    validate_structured_output,
    validate_text_output,
)


OUTLINE_OUTPUT_SCHEMA = [
    {"name": "outline_refined", "type": "object", "required": True},
    {"name": "node_mappings", "type": "array", "required": True, "itemType": "object"},
    {"name": "change_summary", "type": "string", "required": True},
]


def test_validate_structured_output_passes_with_all_fields():
    payload = {
        "outline_refined": {"schema_version": "1.0", "nodes": []},
        "node_mappings": [],
        "change_summary": "ok",
    }
    validate_structured_output(payload, OUTLINE_OUTPUT_SCHEMA)


def test_validate_structured_output_raises_on_missing_field():
    with pytest.raises(ValidationError, match="change_summary"):
        validate_structured_output(
            {"outline_refined": {}, "node_mappings": []},
            OUTLINE_OUTPUT_SCHEMA,
        )


def test_validate_text_output_requires_non_empty_string():
    validate_text_output("hello")
    with pytest.raises(ValidationError):
        validate_text_output("")
    with pytest.raises(ValidationError):
        validate_text_output(None)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/tongqianni/xlab/tender_skills
.venv/bin/python -m pytest tests/scripts/test_provision_verify.py -v
```

Expected: FAIL — `ModuleNotFoundError: scripts.provision_agent`

- [ ] **Step 3: 实现最小校验函数**

在 `scripts/provision_agent.py` 中先只写校验部分（Task 3 会补全文件，此处先创建文件头部）：

```python
# scripts/provision_agent.py 片段
from __future__ import annotations

class ValidationError(Exception):
    pass


def _field_type_matches(value, field: dict) -> bool:
    ftype = field["type"]
    if ftype == "string":
        return isinstance(value, str)
    if ftype == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if ftype == "boolean":
        return isinstance(value, bool)
    if ftype == "object":
        return isinstance(value, dict)
    if ftype == "array":
        return isinstance(value, list)
    return False


def validate_structured_output(payload: dict, output_schema: list[dict]) -> None:
    if not isinstance(payload, dict):
        raise ValidationError("structuredOutput 必须是 object")
    for field in output_schema:
        name = field["name"]
        if field.get("required") and name not in payload:
            raise ValidationError(f"缺少字段: {name}")
        if name in payload and not _field_type_matches(payload[name], field):
            raise ValidationError(f"字段类型不匹配: {name}")


def validate_text_output(output: str | None) -> None:
    if not output or not str(output).strip():
        raise ValidationError("text output 不能为空")
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/scripts/test_provision_verify.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/provision_agent.py tests/scripts/test_provision_verify.py
git commit -m "feat: add provision agent output validation helpers"
```

---

### Task 2: 试点配置文件 outline_refine.json

**Files:**
- Create: `scripts/agents/outline_refine.json`

- [ ] **Step 1: 创建配置文件**

从设计文档 §6 复制完整 JSON 到 `scripts/agents/outline_refine.json`（含 `verify.input` fixture 与 `pydanticModels`）。

`node_mappings` 的 pydantic 校验在脚本中包装为 `{"mappings": value}` 再调 `OutlineMappingFile.model_validate`。

- [ ] **Step 2: 验证 JSON 可读**

```bash
.venv/bin/python -c "import json; json.load(open('scripts/agents/outline_refine.json'))"
```

Expected: 无异常

- [ ] **Step 3: Commit**

```bash
git add scripts/agents/outline_refine.json
git commit -m "feat: add outline_refine agent platform config"
```

---

### Task 3: provision_agent.py 核心实现

**Files:**
- Modify: `scripts/provision_agent.py`（补全 HTTP、upsert、CLI）

- [ ] **Step 1: 添加配置加载与 HTTP 客户端**

```python
# 追加到 scripts/provision_agent.py
import argparse
import importlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = Path(__file__).resolve().parent / "agents"


def load_dotenv_key(name: str) -> str | None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return os.environ.get(name)
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get(name)


class PlatformClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, body: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} {method} {path}: {detail}") from exc

    def api(self, method: str, path: str, body: dict | None = None) -> Any:
        envelope = self.request(method, path, body)
        if isinstance(envelope, dict) and "code" in envelope:
            if envelope["code"] != 0:
                raise RuntimeError(f"API error {path}: {envelope}")
            return envelope.get("data")
        return envelope


def load_agent_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    prompt_file = cfg.get("promptFile")
    if prompt_file:
        cfg["_systemPrompt"] = (ROOT / prompt_file).read_text(encoding="utf-8")
    elif cfg.get("promptText"):
        cfg["_systemPrompt"] = cfg["promptText"]
    else:
        raise ValidationError("配置需 promptFile 或 promptText")
    return cfg
```

- [ ] **Step 2: 实现模型 / Agent / Application upsert**

```python
def ensure_model(client: PlatformClient, cfg: dict) -> str:
    model_name = cfg["modelName"]
    listed = client.api("POST", "/api/v1/models/list", {"page": 1, "pageSize": 100})
    for item in listed.get("list", []):
        if item.get("modelName") == model_name:
            return item["id"]
    if model_name == "qwen-vl-ocr":
        api_key = load_dotenv_key("LLM_API_KEY") or load_dotenv_key("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("创建 OCR 模型需要 LLM_API_KEY")
        created = client.api(
            "POST",
            "/api/v1/models",
            {
                "name": "千问 qwen-vl-ocr",
                "modelName": "qwen-vl-ocr",
                "type": "qwen",
                "apiKey": api_key,
                "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "streaming": False,
                "thinking": False,
                "temperature": 0.7,
            },
        )
        return created["id"]
    raise RuntimeError(f"平台未找到模型 {model_name}，请先手动创建")


def find_by_en_name(items: list[dict], en_name: str) -> dict | None:
    return next((x for x in items if x.get("enName") == en_name), None)


def upsert_agent(client: PlatformClient, cfg: dict, model_id: str) -> str:
    en_name = cfg["enName"]
    listed = client.api("POST", "/api/v1/agents/list", {"page": 1, "pageSize": 200})
    existing = find_by_en_name(listed.get("list", []), en_name)
    if existing:
        agent_id = existing["id"]
    else:
        created = client.api(
            "POST",
            "/api/v1/agents",
            {"zhName": cfg["zhName"], "enName": en_name, "description": cfg.get("description")},
        )
        agent_id = created["id"]

    draft = cfg["draft"]
    client.api(
        "PATCH",
        f"/api/v1/agents/{agent_id}/draft",
        {
            "prompt": {
                "systemPrompt": cfg["_systemPrompt"],
                "initialMessages": draft.get("initialMessages", []),
            },
            "model": {
                "modelId": model_id,
                "backupModelId": "",
                "temperature": 0.7,
                "thinking": False,
            },
            "io": {
                "formatInput": draft["formatInput"],
                "inputSchema": draft["inputSchema"],
                "formatOutput": draft["formatOutput"],
                "outputSchema": draft.get("outputSchema", []),
            },
            "runtime": draft["runtime"],
            "skills": {"skillIds": []},
        },
    )
    validation = client.api("POST", f"/api/v1/agents/{agent_id}/validate")
    if not validation.get("valid"):
        raise RuntimeError(f"Agent validate 失败: {validation.get('errors')}")
    client.api("POST", f"/api/v1/agents/{agent_id}/publish", {"message": "provision"})
    return agent_id


def upsert_application(client: PlatformClient, cfg: dict, agent_id: str) -> str:
    en_name = cfg["enName"]
    app_cfg = cfg["application"]
    listed = client.api("POST", "/api/v1/applications/list", {"page": 1, "pageSize": 200})
    existing = find_by_en_name(listed.get("list", []), en_name)
    body = {
        "name": cfg["zhName"],
        "enName": en_name,
        "agentId": agent_id,
        "agentVersionRef": {"publishMode": "latest", "version": None},
        "mode": app_cfg.get("mode", "api"),
        "apiConfig": {"syncType": app_cfg.get("syncType", "sync")},
        "concurrency": 10,
        "timeoutMs": app_cfg.get("timeoutMs", 60000),
    }
    if existing:
        app_id = existing["id"]
        client.api("PUT", f"/api/v1/applications/{app_id}", body)
        publish_status = existing.get("publishStatus", "draft")
    else:
        created = client.api("POST", "/api/v1/applications", body)
        app_id = created["id"]
        publish_status = "draft"
    if publish_status != "published":
        client.api("POST", f"/api/v1/applications/{app_id}/publish")
    return app_id
```

- [ ] **Step 3: 实现 verify 与 pydantic 深度校验**

```python
def resolve_pydantic_model(dotted: str):
    module_name, class_name = dotted.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def apply_pydantic_models(payload: dict, mapping: dict[str, str]) -> None:
    for field_name, dotted in mapping.items():
        if field_name not in payload:
            continue
        model_cls = resolve_pydantic_model(dotted)
        value = payload[field_name]
        if model_cls.__name__ == "OutlineMappingFile":
            model_cls.model_validate({"mappings": value})
        else:
            model_cls.model_validate(value)


def verify_agent(client: PlatformClient, cfg: dict) -> None:
    draft = cfg["draft"]
    verify_input = cfg["verify"]["input"]
    resp = client.request(
        "POST",
        "/v1/apps/invoke",
        {"appName": cfg["enName"], "input": verify_input},
    )
    if resp.get("status") != "completed":
        raise ValidationError(f"invoke 未完成: {resp}")
    if draft["formatOutput"]:
        structured = resp.get("structuredOutput")
        validate_structured_output(structured, draft.get("outputSchema", []))
        pydantic_map = cfg.get("verify", {}).get("pydanticModels") or {}
        if pydantic_map:
            apply_pydantic_models(structured, pydantic_map)
    else:
        validate_text_output(resp.get("output"))
```

- [ ] **Step 4: 实现 CLI**

```python
def provision_one(client: PlatformClient, config_path: Path, *, skip_verify: bool) -> None:
    cfg = load_agent_config(config_path)
    print(f"→ {cfg['enName']}: ensure model …")
    model_id = ensure_model(client, cfg)
    print(f"→ {cfg['enName']}: upsert agent …")
    agent_id = upsert_agent(client, cfg, model_id)
    print(f"→ {cfg['enName']}: upsert application …")
    upsert_application(client, cfg, agent_id)
    if skip_verify:
        print(f"✓ {cfg['enName']} provisioned (verify skipped)")
        return
    print(f"→ {cfg['enName']}: verify invoke …")
    verify_agent(client, cfg)
    print(f"✓ {cfg['enName']} provisioned and verified")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision tender_skills agents to df-agent-os")
    parser.add_argument("config", nargs="?", help="Path to agent JSON config")
    parser.add_argument("--all", action="store_true", help="Provision all configs in scripts/agents/")
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("AGENT_PLATFORM_BASE_URL", "http://localhost:8000"))
    args = parser.parse_args(argv)

    if not args.all and not args.config:
        parser.error("需要 config 路径或 --all")

    client = PlatformClient(args.base_url)
    paths = sorted(AGENTS_DIR.glob("*.json")) if args.all else [Path(args.config)]
    failures: list[str] = []
    for path in paths:
        try:
            provision_one(client, path.resolve(), skip_verify=args.skip_verify)
        except Exception as exc:
            failures.append(f"{path.name}: {exc}")
            print(f"✗ {path.name}: {exc}", file=sys.stderr)
    if failures:
        print(f"\n{len(failures)} failed:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Commit**

```bash
git add scripts/provision_agent.py
git commit -m "feat: implement provision_agent upsert and verify flow"
```

---

### Task 4: 试点集成验证 outline_refine

**前置:** df-agent-os-python 在 `localhost:8000` 运行；`.env` 含有效 `LLM_API_KEY`。

- [ ] **Step 1: 健康检查**

```bash
curl -s http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 2: 执行 provision + verify**

```bash
cd /Users/tongqianni/xlab/tender_skills
.venv/bin/python scripts/provision_agent.py scripts/agents/outline_refine.json
```

Expected: 三行 `→` + `✓ outline_refine provisioned and verified`

- [ ] **Step 3: 幂等重跑**

```bash
.venv/bin/python scripts/provision_agent.py scripts/agents/outline_refine.json
```

Expected: 再次成功，agent `publishedVersion` 递增

- [ ] **Step 4: 手动 curl 验证**

```bash
curl -s -X POST http://localhost:8000/v1/apps/invoke \
  -H 'Content-Type: application/json' \
  -d @- <<'EOF'
{
  "appName": "outline_refine",
  "input": {
    "instruction": "重命名第一章",
    "original_outline": {
      "schema_version": "1.0",
      "strategy": "heading_heuristic",
      "nodes": [{"node_id": "n1", "title": "第一章", "level": 1, "parent_id": null, "sort_order": 0, "anchor": {"block_index": 0}, "needs_review": false, "source_refs": []}]
    },
    "current_outline": {
      "schema_version": "1.0",
      "strategy": "heading_heuristic",
      "nodes": [{"node_id": "n1", "title": "第一章", "level": 1, "parent_id": null, "sort_order": 0, "anchor": {"block_index": 0}, "needs_review": false, "source_refs": []}]
    }
  }
}
EOF
```

Expected: `"status":"completed"`，`structuredOutput` 含 `outline_refined` / `node_mappings` / `change_summary`

- [ ] **Step 5: Commit（若有微调）**

```bash
git add -A && git commit -m "fix: tune outline_refine provision after pilot"
```

---

### Task 5: doc_chunk 系列配置（2 个）

**Files:**
- Create: `scripts/agents/chunk_classify.json`
- Create: `scripts/agents/chunk_describe.json`

- [ ] **Step 1: chunk_classify.json**

| 字段 | 值 |
|------|-----|
| promptText | 见 `docs/agent_requirements.md` §4.2 user prompt 规则；system 无，用 user 模板作 initialMessages：`请将以下文本分类…\n{{title}}\n{{markdown}}` |
| formatInput | true |
| inputSchema | `title`(string), `markdown`(string) |
| formatOutput | true |
| outputSchema | `knowledge_type`, `chapter_type`, `confidence`, `rationale` |
| verify.input | 短 markdown fixture |

- [ ] **Step 2: chunk_describe.json**

| 字段 | 值 |
|------|-----|
| formatOutput | **false**（text 输出） |
| initialMessages | `[{"role":"user","mode":"text","content":"请基于以下文档块…\n标题: {{title}}\n正文:\n{{markdown}}"}]` |
| verify | 断言 `output` 非空 string |

- [ ] **Step 3: 逐个 provision + verify**

```bash
.venv/bin/python scripts/provision_agent.py scripts/agents/chunk_classify.json
.venv/bin/python scripts/provision_agent.py scripts/agents/chunk_describe.json
```

- [ ] **Step 4: Commit**

```bash
git add scripts/agents/chunk_classify.json scripts/agents/chunk_describe.json
git commit -m "feat: add chunk_classify and chunk_describe agent configs"
```

---

### Task 6: interpret 系列配置（3 个）

**Files:**
- Create: `scripts/agents/interpret_segment.json`
- Create: `scripts/agents/interpret_scoring_table.json`
- Create: `scripts/agents/interpret_overview.json`

- [ ] **Step 1: interpret_segment.json**

- `promptText`: `src/tender_insights/interpret/prompts.py` 的 `SYSTEM_PROMPT`
- `initialMessages`: user 模板含 `{{segment_id}}`, `{{section_path}}`, `{{markdown}}`
- `outputSchema`: 四大数组字段顶层（`disqualification_items`, `scoring_items`, `bid_risk_items`, `directory_requirements`）
- `verify.pydanticModels`: `"__root__": "tender_insights.interpret.models:InterpretationLLMResponse"` 或在脚本中支持 root 校验

**脚本小扩展:** 在 `apply_pydantic_models` 增加 `"__root__"` 键时对整包 `structuredOutput` 做 validate。

- [ ] **Step 2: interpret_scoring_table.json**

- 同 interpret_segment，`promptText` 追加 `_SCORING_TABLE_ONLY_APPENDIX` 文本
- `initialMessages` 固定 appendix 已 baked 进 systemPrompt

- [ ] **Step 3: interpret_overview.json**

- `promptText`: `interpret/overview.py` 内 SYSTEM_PROMPT
- `outputSchema`: 五个 summary 字符串字段

- [ ] **Step 4: provision 全部并 commit**

```bash
.venv/bin/python scripts/provision_agent.py scripts/agents/interpret_segment.json
.venv/bin/python scripts/provision_agent.py scripts/agents/interpret_scoring_table.json
.venv/bin/python scripts/provision_agent.py scripts/agents/interpret_overview.json
git add scripts/agents/interpret_*.json scripts/provision_agent.py
git commit -m "feat: add interpret agent configs and root pydantic verify"
```

---

### Task 7: brief 系列配置（3 个）

**Files:**
- Create: `scripts/agents/brief_single.json`
- Create: `scripts/agents/brief_segment.json`
- Create: `scripts/agents/brief_merge.json`

- [ ] **Step 1: 从 `src/tender_insights/brief/prompts.py` 提取 SYSTEM prompt**

- `brief_single`: `SINGLE_SYSTEM_PROMPT`（`{max_chars}` 在配置中用 500 替换）
- `brief_segment`: `EXTRACT_SYSTEM_PROMPT`
- `brief_merge`: `MERGE_SYSTEM_PROMPT`（max_chars=500）

- [ ] **Step 2: 定义 inputSchema / outputSchema / verify fixture**

- single/merge 输出: `fields` + `summary_text`
- segment 输出: 五个 string 数组

- [ ] **Step 3: provision 并 commit**

```bash
.venv/bin/python scripts/provision_agent.py scripts/agents/brief_single.json
.venv/bin/python scripts/provision_agent.py scripts/agents/brief_segment.json
.venv/bin/python scripts/provision_agent.py scripts/agents/brief_merge.json
git add scripts/agents/brief_*.json
git commit -m "feat: add brief agent configs"
```

---

### Task 8: template + legal + gen_catalog 系列（8 个）

**Files:**
- Create: `scripts/agents/template_plan.json`
- Create: `scripts/agents/template_extract.json`
- Create: `scripts/agents/gen_catalog_initial.json`
- Create: `scripts/agents/gen_catalog_node_plan.json`
- Create: `scripts/agents/gen_catalog_node_apply.json`
- Create: `scripts/agents/legal_section_review.json`

Prompt 来源:

| 配置 | Prompt 源 |
|------|-----------|
| template_plan | `src/tender_insights/template/planner.py` |
| template_extract | `src/tender_insights/template/extractor.py` |
| gen_catalog_* | `src/tender_insights/gen_catalog/prompts.py` |
| legal_section_review | `src/tender_insights/legal/prompts.py` |

- [ ] **Step 1: 按 `docs/agent_requirements.md` §4.10–§4.15 逐个编写 JSON**

- [ ] **Step 2: 批量 provision**

```bash
for f in scripts/agents/{template,gen_catalog,legal}_*.json scripts/agents/gen_catalog_*.json; do
  .venv/bin/python scripts/provision_agent.py "$f" || exit 1
done
```

- [ ] **Step 3: Commit**

```bash
git add scripts/agents/template_*.json scripts/agents/gen_catalog_*.json scripts/agents/legal_section_review.json
git commit -m "feat: add template, gen_catalog, and legal agent configs"
```

---

### Task 9: OCR 智能体配置

**Files:**
- Create: `scripts/agents/ocr_image_recognize.json`

- [ ] **Step 1: 创建 multimodal 配置**

参考平台已有 `image_recognize` draft:

```json
{
  "promptText": "请识别图片中的全部文字，按阅读顺序输出纯文本，不要解释。",
  "modelName": "qwen-vl-ocr",
  "draft": {
    "formatInput": true,
    "inputSchema": [
      {"id": "f1", "name": "image_url", "type": "string", "required": true, "description": "data URI 或 HTTP URL"}
    ],
    "formatOutput": false,
    "initialMessages": [
      {
        "id": "msg_ocr",
        "role": "user",
        "mode": "multimodal",
        "content": "[{\"type\":\"text\",\"text\":\"请识别图片中的全部文字，按阅读顺序输出纯文本，不要解释。\"},{\"type\":\"image_url\",\"image_url\":{\"url\":\"{{image_url}}\"}}]"
      }
    ],
    "runtime": {"retryCount": 0, "timeoutMs": 120000, "streaming": false, "multiTurn": false}
  },
  "verify": {
    "input": {
      "image_url": "https://agent.mengxiang.com/ai-admin/images/logo.png"
    }
  }
}
```

- [ ] **Step 2: provision（会自动创建 qwen-vl-ocr 模型）**

```bash
.venv/bin/python scripts/provision_agent.py scripts/agents/ocr_image_recognize.json
```

- [ ] **Step 3: Commit**

```bash
git add scripts/agents/ocr_image_recognize.json
git commit -m "feat: add ocr_image_recognize agent config"
```

---

### Task 10: 全量验证与文档

**Files:**
- Modify: `docs/superpowers/specs/2026-07-05-tender-agents-platform-provision-design.md`（状态改为「已实现」，可选）

- [ ] **Step 1: 全量 provision**

```bash
.venv/bin/python scripts/provision_agent.py --all
```

Expected: 16 个全部 `✓ … provisioned and verified`

- [ ] **Step 2: 运行单元测试**

```bash
.venv/bin/python -m pytest tests/scripts/test_provision_verify.py -v
```

- [ ] **Step 3: 更新设计文档状态行**

```markdown
> 状态：已实现（2026-07-05）
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-05-tender-agents-platform-provision-design.md
git commit -m "docs: mark agent platform provision design as implemented"
```

---

## Spec 覆盖自检

| 设计 § | 对应 Task |
|--------|-----------|
| §2 单脚本 + 16 配置 | Task 3, 5–9 |
| §3 CLI 接口 | Task 3 Step 4 |
| §4 Provision 流程 | Task 3 Step 2 |
| §5 验证规则 | Task 1, 3 Step 3 |
| §6 配置格式 | Task 2, 5–9 |
| §7 16 清单 | Task 2, 5–9 |
| §8 实施顺序 | Task 4→10 |
| §10 错误处理 | Task 3 main() failures 汇总 |
| §11 测试计划 | Task 1, 4, 10 |

---

## 平台升级建议（实现时不阻塞）

记录于设计文档 §9，不在本计划实现范围内：

1. `runtime.responseFormat: json`
2. 运行时 `outputSchema` 校验
