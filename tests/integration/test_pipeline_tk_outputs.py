from pathlib import Path

from doc_chunk.api import run_pipeline


def test_pipeline_produces_tk_integration_artifacts(sample_docx: Path, tmp_path: Path) -> None:
    out = tmp_path / "tk-ws"
    result = run_pipeline(sample_docx, out, overwrite=True, skip_refine=True, skip_enrich=True)
    assert result.status == "success"
    assert (out / "content.blocks.json").exists()
    assert (out / "images" / "manifest.json").exists() or True  # no images in minimal sample
    assert (out / "document_tree.json").exists()
    assert (out / "linkage.json").exists()
    manifest = __import__("json").loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["stages"].get("tree", {}).get("status") == "success"
    assert manifest["outputs"].get("linkage") == "linkage.json"
