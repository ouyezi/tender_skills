from doc_chunk.config import ChunkConfig
from doc_chunk.errors import UnsupportedFormatError, WorkspaceError


def test_unsupported_format_is_doc_chunk_error():
    err = UnsupportedFormatError("bad file")
    assert "bad file" in str(err)


def test_default_chunk_max_tokens():
    assert ChunkConfig().max_tokens == 20_000


def test_workspace_error_subclass():
    err = WorkspaceError("exists")
    assert isinstance(err, WorkspaceError)
