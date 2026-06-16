from __future__ import annotations

from pathlib import Path

import pytest

from viewer.config import ViewerSettings


def test_settings_use_env_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DOC_CHUNK_VIEWER_DATA", str(tmp_path))
    settings = ViewerSettings.load()
    assert settings.data_dir == tmp_path.resolve()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8765
    assert settings.max_sessions == 20
