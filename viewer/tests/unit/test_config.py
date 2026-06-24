from __future__ import annotations

from pathlib import Path

import pytest

from viewer.config import ViewerSettings, load_project_env


def test_load_project_env_reads_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_API_KEY=sk-from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    loaded = load_project_env()
    assert loaded == env_file
    import os

    assert os.environ["LLM_API_KEY"] == "sk-from-dotenv"


def test_load_project_env_does_not_override_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-existing")
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_API_KEY=sk-from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    load_project_env()
    import os

    assert os.environ["LLM_API_KEY"] == "sk-existing"


def test_settings_use_env_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DOC_CHUNK_VIEWER_DATA", str(tmp_path))
    settings = ViewerSettings.load()
    assert settings.data_dir == tmp_path.resolve()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8765
    assert settings.max_sessions == 20
