from doc_chunk.chunk.blocks_builder import build_chunk_blocks

MAX = 32_000


def test_build_chunk_blocks_splits_types_and_truncates() -> None:
    long_text = "x" * (MAX + 100)
    blocks = build_chunk_blocks(
        markdown=f"段落。\n\n|a|b|\n\n![img](images/i.png)\n\n{long_text}",
    )
    types = [b.type for b in blocks]
    assert "paragraph" in types
    assert "table" in types
    assert "image" in types
    assert all(len(b.text or "") <= MAX for b in blocks if b.type != "image")
