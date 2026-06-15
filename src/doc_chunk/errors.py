class DocChunkError(Exception):
    """Base error for doc_chunk."""


class UnsupportedFormatError(DocChunkError):
    pass


class WorkspaceError(DocChunkError):
    pass


class LLMUnavailableError(DocChunkError):
    pass


class ValidationError(DocChunkError):
    pass
