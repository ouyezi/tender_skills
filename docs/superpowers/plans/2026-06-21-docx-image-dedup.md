# Docx Inline Image Dedup Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix Word inline image extraction so paragraph-internal duplicate blips dedupe while cross-placement rId reuse still emits Markdown blocks.

**Architecture:** Keep element-scoped blip dedup in `_docx_element_image_embeds`; refactor `_register_docx_image` to always emit blocks but save files once per `r:embed`; remove table-level rId dedup.

**Tech Stack:** Python 3, python-docx, pytest, existing `doc_chunk.extract.docx_extractor`

**Spec:** `docs/superpowers/specs/2026-06-21-docx-image-dedup-design.md`

---

## File Map

| File | Action |
|------|--------|
| `src/doc_chunk/extract/docx_extractor.py` | Refactor `_register_docx_image`, simplify `_docx_table_image_embeds` |
| `tests/conftest.py` | Add fixtures for intra-paragraph dup, cross-paragraph reuse, body+table reuse |
| `tests/unit/test_docx_extractor.py` | Update + add unit tests |
| `tests/integration/test_dingxin_image_regression.py` | Optional Dingxin section regression |

---

### Task 1: Intra-paragraph dedup test + register refactor

**Files:**
- Modify: `src/doc_chunk/extract/docx_extractor.py`
- Modify: `tests/conftest.py`
- Modify: `tests/unit/test_docx_extractor.py`

- [ ] **Step 1: Add fixture `sample_docx_with_duplicate_blip_in_paragraph`**

Duplicate `a:blip` inside one paragraph via `copy.deepcopy` on blip node.

- [ ] **Step 2: Add failing test `test_extract_docx_deduplicates_repeated_embed_in_paragraph`**

Assert: `image_count == 1`, 1 file on disk, 1 `![` in content.

- [ ] **Step 3: Refactor `_register_docx_image`**

Always increment placement counter and `acc.add_image()`; save file only when `relationship_id` not in map; file number = `len(relationship_to_image_ref) + 1` on first sight.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/test_docx_extractor.py -v`

---

### Task 2: Cross-placement reuse tests

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/unit/test_docx_extractor.py`
- Modify: `src/doc_chunk/extract/docx_extractor.py` (`_docx_table_image_embeds`)

- [ ] **Step 1: Update `test_extract_docx_deduplicates_repeated_embed_references`**

Assert: `image_count == 2`, 1 file, 2 markdown image lines (same `image_ref`).

- [ ] **Step 2: Add `test_extract_docx_reuses_file_across_paragraphs`**

Two `add_picture` same PNG → 2 blocks, 1 file.

- [ ] **Step 3: Remove table-level `seen_relationship_ids`**

- [ ] **Step 4: Add `test_extract_docx_table_reuses_rids_from_body`**

Body paragraph + table cell, same PNG → 2 blocks, 1 file.

- [ ] **Step 5: Run unit tests**

Run: `.venv/bin/python -m pytest tests/unit/test_docx_extractor.py -v`

---

### Task 3: Optional Dingxin integration regression

**Files:**
- Create: `tests/integration/test_dingxin_image_regression.py`

- [ ] **Step 1: Add skip-if-no-env test**

`DOC_CHUNK_DINGXIN_FIXTURE` → extract → assert section 四 has 4 `![`, section 五 has 2.

- [ ] **Step 2: Run locally with fixture path**

Run: `DOC_CHUNK_DINGXIN_FIXTURE=/path/to/鼎信餐补标书.converted.docx .venv/bin/python -m pytest tests/integration/test_dingxin_image_regression.py -v`

---

### Task 4: Commit

- [ ] **Step 1: Commit implementation**

```bash
git add src/doc_chunk/extract/docx_extractor.py tests/conftest.py tests/unit/test_docx_extractor.py tests/integration/test_dingxin_image_regression.py
git commit -m "fix(extract): dedupe inline blips per paragraph, emit reused rIds at each placement"
```
