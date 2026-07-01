from doc_chunk.table.access import load_table_model, substitute_tables_for_llm
from doc_chunk.table.assets import collect_table_assets
from doc_chunk.table.patch import PatchResult, patch_docx_tables

__all__ = [
    "PatchResult",
    "collect_table_assets",
    "load_table_model",
    "patch_docx_tables",
    "substitute_tables_for_llm",
]
