from pathlib import Path

from doc_chunk.api import run_pipeline
from doc_chunk.metadata.classify import classify_chunk


def test_on_progress_receives_stage_messages(sample_docx: Path, tmp_path: Path) -> None:
    events: list[tuple[str, dict]] = []
    run_pipeline(
        sample_docx,
        tmp_path / "prog",
        overwrite=True,
        skip_refine=True,
        skip_enrich=True,
        on_progress=lambda stage, payload: events.append((stage, payload)),
    )
    stages = {s for s, _ in events}
    assert {"extract", "outline", "tree", "chunk"} <= stages
    chunk_events = [p for s, p in events if s == "chunk"]
    assert any("current" in p for p in chunk_events)


def test_on_progress_exception_does_not_fail_pipeline(sample_docx: Path, tmp_path: Path) -> None:
    def bad_cb(stage, payload):
        raise RuntimeError("boom")

    result = run_pipeline(
        sample_docx,
        tmp_path / "prog2",
        overwrite=True,
        skip_refine=True,
        skip_enrich=True,
        on_progress=bad_cb,
    )
    assert result.status == "success"


def test_classification_config_emits_hints(tmp_path: Path) -> None:
    cfg = tmp_path / "hints.yaml"
    cfg.write_text(
        """
product_categories:
  - aliases: ["餐补", "福利餐"]
    hint: "餐补平台"
chapter_taxonomies:
  - aliases: ["技术方案", "系统设计"]
    hint: "技术方案"
""",
        encoding="utf-8",
    )
    result = classify_chunk(
        title="餐补技术方案",
        markdown="福利餐平台实施方案",
        llm_client=None,
        classification_config=cfg,
    )
    assert "餐补平台" in result.get("product_category_hints", [])
    assert "技术方案" in result.get("chapter_taxonomy_hints", [])
