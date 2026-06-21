from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from doc_chunk.extract.docx_extractor import extract_docx
from doc_chunk.workspace.layout import OutputWorkspace

DINGXIN = os.environ.get("DOC_CHUNK_DINGXIN_FIXTURE")


def _section_image_count(content: str, start_title: str, end_title: str) -> int:
    start = content.find(start_title)
    end = content.find(end_title, start + len(start_title))
    if start < 0 or end < 0:
        raise AssertionError(f"section markers not found: {start_title!r} -> {end_title!r}")
    segment = content[start:end]
    return len(re.findall(r"!\[[^\]]*\]\([^)]+\)", segment))


@pytest.mark.skipif(not DINGXIN, reason="set DOC_CHUNK_DINGXIN_FIXTURE to run dingxin image regression")
def test_dingxin_authorization_sections_emit_expected_image_blocks(tmp_path: Path) -> None:
    src = Path(DINGXIN)
    ws = OutputWorkspace.create(tmp_path / "dingxin", overwrite=True)
    result = extract_docx(src, ws)
    content = ws.content_path.read_text(encoding="utf-8")

    section_four = _section_image_count(
        content,
        "四、法定代表人（单位负责人）授权书",
        "五、法定代表人（单位负责人）身份证明",
    )
    section_five = _section_image_count(
        content,
        "五、法定代表人（单位负责人）身份证明",
        "六、",
    )

    assert section_four == 4
    assert section_five == 2
    assert section_four + section_five <= result.image_count
