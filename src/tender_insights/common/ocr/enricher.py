from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

from PIL import Image

from doc_chunk.workspace.layout import OutputWorkspace

from tender_insights.common.ocr.client import OcrClient
from tender_insights.common.ocr.models import OcrCacheEntry, OcrCacheFile
from tender_insights.config import InsightsConfig

_IMAGE_REF_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")
_OCR_BLOCK_RE = re.compile(r"\n\n<!-- ocr:[a-f0-9]+ -->\n.*?\n<!-- /ocr -->", re.DOTALL)


def list_image_refs(content_md: str) -> list[str]:
    seen: set[str] = set()
    refs: list[str] = []
    for match in _IMAGE_REF_RE.finditer(content_md):
        ref = match.group(1).strip()
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def _is_logo_skip(width: int, height: int, size_bytes: int, *, max_bytes: int, max_px: int) -> bool:
    return size_bytes <= max_bytes and (width < max_px or height < max_px)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _mime_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")


def _compress_image_bytes(raw: bytes, *, max_long_edge: int) -> tuple[bytes, str]:
    with Image.open(io.BytesIO(raw)) as img:
        fmt = (img.format or "PNG").upper()
        mime = f"image/{fmt.lower()}" if fmt != "JPEG" else "image/jpeg"
        width, height = img.size
        long_edge = max(width, height)
        if long_edge > max_long_edge:
            scale = max_long_edge / long_edge
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        save_fmt = "PNG" if fmt not in {"PNG", "JPEG", "WEBP", "GIF"} else fmt
        img.save(out, format=save_fmt)
        return out.getvalue(), mime if save_fmt != "JPEG" else "image/jpeg"


def _resolve_image_path(workspace: OutputWorkspace, image_ref: str) -> Path:
    ref = image_ref.lstrip("/")
    if ref.startswith("images/"):
        return workspace.root / ref
    return workspace.images_dir / Path(ref).name


def _load_cache(workspace: OutputWorkspace) -> OcrCacheFile:
    cache_path = workspace.root / "interpret" / "ocr_cache.json"
    if not cache_path.exists():
        return OcrCacheFile()
    return OcrCacheFile.model_validate_json(cache_path.read_text(encoding="utf-8"))


def _save_cache(workspace: OutputWorkspace, cache: OcrCacheFile) -> None:
    interpret_dir = workspace.root / "interpret"
    interpret_dir.mkdir(parents=True, exist_ok=True)
    cache_path = interpret_dir / "ocr_cache.json"
    cache_path.write_text(cache.model_dump_json(indent=2), encoding="utf-8")


def _ocr_text_for_ref(
    workspace: OutputWorkspace,
    image_ref: str,
    *,
    config: InsightsConfig,
    cache: OcrCacheFile,
    client: OcrClient,
    api_calls: list[int],
) -> OcrCacheEntry:
    path = _resolve_image_path(workspace, image_ref)
    if not path.is_file():
        return OcrCacheEntry(
            image_ref=image_ref,
            status="failed",
            skipped_reason="missing_file",
        )

    file_hash = _file_sha256(path)
    existing = cache.entries.get(file_hash)
    if existing is not None:
        return existing

    size_bytes = path.stat().st_size
    with Image.open(path) as img:
        width, height = img.size

    if _is_logo_skip(
        width,
        height,
        size_bytes,
        max_bytes=config.ocr_logo_max_bytes,
        max_px=config.ocr_logo_max_px,
    ):
        entry = OcrCacheEntry(
            image_ref=image_ref,
            status="skipped",
            skipped_reason="logo",
        )
        cache.entries[file_hash] = entry
        return entry

    try:
        raw = path.read_bytes()
        compressed, mime = _compress_image_bytes(raw, max_long_edge=config.ocr_max_long_edge)
        api_calls[0] += 1
        text = client.recognize_image_bytes(compressed, mime=mime)
        entry = OcrCacheEntry(
            image_ref=image_ref,
            text=text,
            status="success",
            model=config.ocr_model,
        )
    except Exception:
        entry = OcrCacheEntry(
            image_ref=image_ref,
            status="failed",
            skipped_reason="ocr_error",
            model=config.ocr_model,
        )

    cache.entries[file_hash] = entry
    return entry


def _insert_ocr_blocks(content_md: str, ref_to_hash: dict[str, str], ref_to_text: dict[str, str]) -> str:
    lines = content_md.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        out.append(line)
        match = _IMAGE_REF_RE.search(line)
        if not match:
            continue
        ref = match.group(1).strip()
        text = ref_to_text.get(ref, "").strip()
        file_hash = ref_to_hash.get(ref)
        if not text or not file_hash:
            continue
        out.append(f"\n<!-- ocr:{file_hash} -->\n{text}\n<!-- /ocr -->\n")
    return "".join(out)


def enrich_content_with_ocr(
    workspace: OutputWorkspace,
    content_md: str,
    *,
    config: InsightsConfig,
    client: OcrClient | None = None,
) -> tuple[str, OcrCacheFile, int]:
    """Returns (source_content_md, cache, ocr_api_call_count)."""
    cache = _load_cache(workspace)
    ocr_client = client or OcrClient.from_env(model=config.ocr_model)
    api_calls = [0]

    ref_to_hash: dict[str, str] = {}
    ref_to_text: dict[str, str] = {}

    for ref in list_image_refs(content_md):
        path = _resolve_image_path(workspace, ref)
        if not path.is_file():
            continue
        file_hash = _file_sha256(path)
        ref_to_hash[ref] = file_hash
        entry = _ocr_text_for_ref(
            workspace,
            ref,
            config=config,
            cache=cache,
            client=ocr_client,
            api_calls=api_calls,
        )
        if entry.status == "success":
            ref_to_text[ref] = entry.text

    enriched = _insert_ocr_blocks(content_md, ref_to_hash, ref_to_text)
    _save_cache(workspace, cache)
    return enriched, cache, api_calls[0]
