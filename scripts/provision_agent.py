from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = Path(__file__).resolve().parent / "agents"


class ValidationError(Exception):
    pass


def _field_type_matches(value: Any, field: dict) -> bool:
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


def load_dotenv_key(name: str) -> str | None:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
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
            with urllib.request.urlopen(req, timeout=180) as resp:
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
    listed = client.api("POST", "/api/v1/agents/list", {"page": 1, "pageSize": 100})
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
    listed = client.api("POST", "/api/v1/applications/list", {"page": 1, "pageSize": 100})
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


_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def parse_json_object(text: str) -> dict | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    candidates = [stripped]
    candidates.extend(m.group(1).strip() for m in _JSON_FENCE.finditer(stripped) if m.group(1).strip())
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _coerce_structured_output(resp: dict) -> dict | None:
    structured = resp.get("structuredOutput")
    if isinstance(structured, dict):
        return structured
    return parse_json_object(str(resp.get("output") or ""))
    module_name, class_name = dotted.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def resolve_pydantic_model(dotted: str):
    module_name, class_name = dotted.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def apply_pydantic_models(payload: dict, mapping: dict[str, str]) -> None:
    for field_name, dotted in mapping.items():
        model_cls = resolve_pydantic_model(dotted)
        if field_name == "__root__":
            model_cls.model_validate(payload)
            continue
        if field_name not in payload:
            continue
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
        structured = _coerce_structured_output(resp)
        validate_structured_output(structured, draft.get("outputSchema", []))
        pydantic_map = cfg.get("verify", {}).get("pydanticModels") or {}
        if pydantic_map:
            apply_pydantic_models(structured, pydantic_map)
    else:
        validate_text_output(resp.get("output"))


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
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AGENT_PLATFORM_BASE_URL", "http://localhost:8000"),
    )
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
