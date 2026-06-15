from pathlib import Path

from doc_chunk.errors import UnsupportedFormatError

_SUFFIX_MAP = {
    ".docx": "docx",
    ".doc": "doc",
    ".docm": "docm",
    ".pdf": "pdf",
}


def detect_file_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in _SUFFIX_MAP:
        raise UnsupportedFormatError(f"Unsupported file type: {suffix}")
    return _SUFFIX_MAP[suffix]
