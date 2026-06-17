import pytest
from docx import Document

from doc_chunk.convert.table_to_docx import render_table_to_docx
from doc_chunk.models.table_model import TableCell, TableGridRow


def test_render_table_to_docx_not_implemented_yet():
    doc = Document()
    grid = {"rows": [TableGridRow(cells=[TableCell(text="a")]).model_dump()]}
    with pytest.raises(NotImplementedError):
        render_table_to_docx(doc, grid, grid_width=1)
