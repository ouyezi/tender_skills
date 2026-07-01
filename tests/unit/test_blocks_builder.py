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


def test_build_chunk_blocks_parses_table_ref_placeholder() -> None:
    markdown = (
        "<!-- table-ref:tables/t0001.json -->\n"
        "| a | b |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n"
    )
    blocks = build_chunk_blocks(markdown=markdown)
    assert len(blocks) == 1
    assert blocks[0].type == "table"
    assert blocks[0].table_ref == "tables/t0001.json"
    assert blocks[0].text is not None
    assert blocks[0].text.startswith("| a | b |")


def test_build_chunk_blocks_table_without_placeholder_has_no_ref() -> None:
    blocks = build_chunk_blocks(markdown="| a | b |\n| --- | --- |\n| 1 | 2 |")
    assert blocks[0].type == "table"
    assert blocks[0].table_ref is None
