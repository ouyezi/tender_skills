from __future__ import annotations

from collections.abc import Iterator

from docx.oxml.ns import qn
from lxml.etree import _Element as OxmlElement

EMBED_ATTR = qn("r:embed")
LINK_ATTR = qn("r:link")
STYLE_VAL_ATTR = qn("w:val")
STYLE_LIKE = {qn("w:tblStyle"), qn("w:pStyle"), qn("w:rStyle"), qn("w:tcStyle")}


def iter_tbl_elements(tbl: OxmlElement) -> Iterator[OxmlElement]:
    yield tbl
    for el in tbl.iter():
        if el is not tbl:
            yield el


def collect_embed_relationship_ids(tbl: OxmlElement) -> set[str]:
    ids: set[str] = set()
    for el in iter_tbl_elements(tbl):
        for attr in (EMBED_ATTR, LINK_ATTR):
            val = el.get(attr)
            if val:
                ids.add(val)
    return ids


def collect_style_ids_from_tbl(tbl: OxmlElement) -> set[str]:
    ids: set[str] = set()
    for el in iter_tbl_elements(tbl):
        if el.tag in STYLE_LIKE:
            val = el.get(STYLE_VAL_ATTR)
            if val:
                ids.add(val)
    return ids
