import pytest
from pathlib import Path

from doc_chunk.api import extract_file
from doc_chunk.errors import UnsupportedFormatError


def test_docm_raises_unsupported_format(tmp_path: Path, sample_docx: Path) -> None:
    docm = tmp_path / "sample.docm"
    docm.write_bytes(sample_docx.read_bytes())
    with pytest.raises(UnsupportedFormatError, match="docm"):
        extract_file(docm, tmp_path / "out", overwrite=True)
