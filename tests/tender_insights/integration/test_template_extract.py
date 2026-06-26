import json
import shutil
from pathlib import Path

from doc_chunk.api import run_pipeline
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.template.extractor import extract_templates_workspace
from tests.helpers.template_fake_llm import TemplateFakeLLM

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
COARSE_OUTLINE_FIXTURE = FIXTURES / "template_coarse_outline"


def test_extract_templates_llm_pipeline(tmp_path, sample_docx, monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATE_PLAN_ENABLED", "false")
    ws_dir = tmp_path / "ws"
    run_pipeline(sample_docx, ws_dir, overwrite=True, skip_refine=True, skip_enrich=True)
    workspace = OutputWorkspace.open_existing(ws_dir)

    extract_json = json.dumps(
        {
            "templates": [
                {
                    "title": "授权书",
                    "type": "authorization",
                    "type_label": "授权书",
                    "markdown": "# 授权书\n\n本授权书声明…",
                    "confidence": 0.9,
                    "source_excerpt": "授权",
                }
            ]
        }
    )
    client = TemplateFakeLLM(
        plan_json='{"shard_count":1,"priority_sections":[],"notes":""}',
        extract_json=extract_json,
    )
    result = extract_templates_workspace(workspace, client)
    assert len(result.templates) >= 1
    assert (ws_dir / "templates" / "plan.json").exists()
    assert (ws_dir / "templates" / "index.json").exists()
    assert result.schema_version == "1.1"
    md_path = workspace.root / result.templates[0].file
    assert md_path.is_file()
    assert "授权书" in md_path.read_text(encoding="utf-8")


def test_extract_templates_coarse_outline(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATE_WHOLE_DOC_MAX_CHARS", "500")
    monkeypatch.setenv("TEMPLATE_PLAN_ENABLED", "false")

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    shutil.copy(COARSE_OUTLINE_FIXTURE / "content.md", ws_dir / "content.md")
    shutil.copy(COARSE_OUTLINE_FIXTURE / "outline.json", ws_dir / "outline.json")
    shutil.copy(FIXTURES / "expected" / "manifest_minimal.json", ws_dir / "manifest.json")

    extract_json = json.dumps(
        {
            "templates": [
                {
                    "title": "授权书",
                    "type": "authorization",
                    "type_label": "授权书",
                    "markdown": "## 授权书\n\n授权正文",
                    "confidence": 0.95,
                    "source_excerpt": "授权",
                },
                {
                    "title": "声明函",
                    "type": "declaration",
                    "type_label": "声明函",
                    "markdown": "## 声明函\n\n声明正文",
                    "confidence": 0.92,
                    "source_excerpt": "声明",
                },
            ]
        }
    )
    client = TemplateFakeLLM(
        plan_json='{"shard_count":6,"priority_sections":["第四章 投标文件格式"],"notes":""}',
        extract_json=extract_json,
    )
    workspace = OutputWorkspace.open_existing(ws_dir)
    result = extract_templates_workspace(workspace, client)

    assert len(result.templates) == 2
    assert {t.title for t in result.templates} == {"授权书", "声明函"}
    assert (ws_dir / "templates" / "plan.json").exists()
    plan = json.loads((ws_dir / "templates" / "plan.json").read_text(encoding="utf-8"))
    assert plan["shard_count"] == 6
