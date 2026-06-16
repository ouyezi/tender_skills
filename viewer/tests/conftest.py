from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

_conftest_path = ROOT / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location("repo_root_conftest", _conftest_path)
assert _spec is not None and _spec.loader is not None
_root_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_root_conftest)


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    return _root_conftest._build_sample_docx(tmp_path / "sample.docx", include_image=False)


@pytest.fixture
def viewer_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DOC_CHUNK_VIEWER_DATA", str(tmp_path))
    return tmp_path
