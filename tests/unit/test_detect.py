from pathlib import Path

from doc_chunk.errors import UnsupportedFormatError
from doc_chunk.extract.detect import detect_file_type
import pytest


def test_detect_docx(tmp_path: Path):
    path = tmp_path / "a.docx"
    path.write_bytes(b"PK")
    assert detect_file_type(path) == "docx"


def test_detect_pdf(tmp_path: Path):
    path = tmp_path / "a.pdf"
    path.write_bytes(b"%PDF")
    assert detect_file_type(path) == "pdf"


def test_reject_unknown(tmp_path: Path):
    path = tmp_path / "a.xyz"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        detect_file_type(path)
