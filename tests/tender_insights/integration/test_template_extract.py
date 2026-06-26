import json

from doc_chunk.api import run_pipeline
from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.template.extractor import extract_templates_workspace
from tests.helpers.template_fake_llm import TemplateFakeLLM


def test_extract_templates_llm_pipeline(tmp_path, sample_docx, monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATE_PLAN_ENABLED", "false")
    ws_dir = tmp_path / "ws"
    run_pipeline(sample_docx, ws_dir, overwrite=True, skip_refine=True, skip_enrich=True)
    workspace = OutputWorkspace.open_existing(ws_dir)

    content_len = len(workspace.content_path.read_text(encoding="utf-8"))
    extract_json = json.dumps(
        {
            "templates": [
                {
                    "title": "授权书",
                    "type": "authorization",
                    "type_label": "授权书",
                    "char_start": 0,
                    "char_end": min(200, content_len),
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
    assert result.plan_ref == "templates/plan.json"
