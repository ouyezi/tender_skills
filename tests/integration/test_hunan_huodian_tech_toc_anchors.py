from __future__ import annotations

from pathlib import Path

import pytest

from doc_chunk.api import extract_file, extract_outline
from doc_chunk.models.outline import OutlineTree
from doc_chunk.locate.heading_starts import infer_body_start

SAMPLE = Path(
    "/Users/tongqianni/xlab/标书助力/测试招投标文件/标书诊断/湖南火电/"
    "湖南火电员工福利商城招标-标书（技术部分）.docx"
)


@pytest.mark.skipif(not SAMPLE.exists(), reason="hunan huodian tech docx not available")
def test_hunan_huodian_tech_anchors_in_body(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    extract_file(SAMPLE, ws, overwrite=True)
    extract_outline(ws)
    content_md = (ws / "content.md").read_text(encoding="utf-8")
    outline = OutlineTree.model_validate_json((ws / "outline.json").read_text(encoding="utf-8"))
    body_start = infer_body_start(content_md)

    titles = ["一、服务方案", "2.兑换平台搭建方案", "（一）服务大纲"]
    hit = 0
    for node in outline.nodes:
        if not any(t.replace(" ", "") in node.title.replace(" ", "") for t in titles):
            continue
        assert node.anchor.char_start is not None
        assert node.anchor.char_start >= body_start
        snippet = content_md[node.anchor.char_start : node.anchor.char_start + 40]
        assert "服务方案1" not in snippet
        hit += 1
    assert hit >= 3
