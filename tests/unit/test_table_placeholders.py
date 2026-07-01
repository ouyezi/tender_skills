from doc_chunk.models.tables_manifest import TableManifestEntry, TablesManifest
from doc_chunk.table.placeholders import (
    TABLE_REF_COMMENT_RE,
    format_table_ref_comment,
    parse_table_ref_from_line,
)


def test_format_table_ref_comment() -> None:
    assert format_table_ref_comment("tables/t0003.json") == "<!-- table-ref:tables/t0003.json -->"


def test_parse_table_ref_from_comment_line() -> None:
    line = "<!-- table-ref:tables/t0003.json -->"
    assert parse_table_ref_from_line(line) == "tables/t0003.json"
    assert parse_table_ref_from_line("| a | b |") is None


def test_table_ref_comment_regex() -> None:
    m = TABLE_REF_COMMENT_RE.search("<!-- table-ref:tables/t0012.json -->")
    assert m is not None
    assert m.group("ref") == "tables/t0012.json"


def test_tables_manifest_model() -> None:
    manifest = TablesManifest(
        tables=[
            TableManifestEntry(
                table_ref="tables/t0000.json",
                source_block_index=0,
                layout_type="simple",
                row_count=2,
                col_count=3,
                char_start=0,
                char_end=100,
                markdown_preview="| a | b |",
            )
        ]
    )
    assert manifest.schema_version == "1.0"
    assert manifest.tables[0].table_ref == "tables/t0000.json"
