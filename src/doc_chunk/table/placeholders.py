from __future__ import annotations

import re

TABLE_REF_COMMENT_RE = re.compile(
    r"<!--\s*table-ref:(?P<ref>tables/t\d{4}\.json)\s*-->"
)
TABLE_REF_TOKEN_RE = re.compile(
    r"⟦table:(?P<ref>tables/t\d{4}\.json)⟧"
)


def format_table_ref_comment(table_ref: str) -> str:
    return f"<!-- table-ref:{table_ref} -->"


def parse_table_ref_from_line(line: str) -> str | None:
    stripped = line.strip()
    for pattern in (TABLE_REF_COMMENT_RE, TABLE_REF_TOKEN_RE):
        match = pattern.search(stripped)
        if match:
            return match.group("ref")
    return None
