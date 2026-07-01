from __future__ import annotations

from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.parts.document import DocumentPart
from lxml.etree import _Element as OxmlElement

from doc_chunk.table.slice_deps import collect_embed_relationship_ids

_STYLE_PART_MARKERS = ("styles", "theme", "fontTable", "numbering", "settings")
_EMBED_ATTRS = (qn("r:embed"), qn("r:link"))


def _is_style_related_part(partname: object) -> bool:
    name = str(partname)
    return any(marker in name for marker in _STYLE_PART_MARKERS)


def graft_style_blobs(source_doc: DocxDocument, dest_doc: DocxDocument) -> None:
    src_by_name = {part.partname: part for part in source_doc.part.package.parts}
    for part in dest_doc.part.package.parts:
        src_part = src_by_name.get(part.partname)
        if src_part is None or not _is_style_related_part(part.partname):
            continue
        part._blob = src_part.blob


def remap_embed_relationships(
    source_part: DocumentPart,
    dest_part: DocumentPart,
    tbl_element: OxmlElement,
) -> None:
    rid_map: dict[str, str] = {}
    for old_rid in collect_embed_relationship_ids(tbl_element):
        if old_rid in rid_map:
            continue
        rel = source_part.rels.get(old_rid)
        if rel is None:
            continue
        rid_map[old_rid] = dest_part.relate_to(rel.target_part, rel.reltype)

    for el in tbl_element.iter():
        for attr in _EMBED_ATTRS:
            old_rid = el.get(attr)
            if old_rid in rid_map:
                el.set(attr, rid_map[old_rid])


def replace_body_with_table(dest_doc: DocxDocument, tbl_element: OxmlElement) -> None:
    body = dest_doc.element.body
    sect_pr = body.sectPr
    for child in list(body):
        body.remove(child)
    body.append(tbl_element)
    if sect_pr is not None:
        body.append(sect_pr)
