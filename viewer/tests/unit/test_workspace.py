from __future__ import annotations

from pathlib import Path

import pytest

from viewer.services.workspace import validate_workspace


def test_validate_workspace_requires_outline_and_content(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "content.md").write_text("# Title\n", encoding="utf-8")

    with pytest.raises(ValueError, match="outline.json"):
        validate_workspace(ws)


def test_validate_workspace_ok(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "content.md").write_text("# Title\n", encoding="utf-8")
    (ws / "outline.json").write_text(
        '{"schema_version":"1.0","strategy":"flat_fallback","nodes":[]}',
        encoding="utf-8",
    )
    assert validate_workspace(ws) == ws.resolve()
