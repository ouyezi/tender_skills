from __future__ import annotations

import json
import shutil
from pathlib import Path

from doc_chunk.models.outline import OutlineNode, OutlineTree
from doc_chunk.workspace.layout import OutputWorkspace


def _separator(file2_name: str) -> str:
    return f"\n\n<!-- source: {file2_name} -->\n"


def _remap_node(node: OutlineNode, *, prefix: str, offset: int, sort_shift: int) -> OutlineNode:
    data = node.model_dump()
    data["node_id"] = f"{prefix}{node.node_id}"
    if node.parent_id:
        data["parent_id"] = f"{prefix}{node.parent_id}"
    data["sort_order"] = node.sort_order + sort_shift
    anchor = dict(data.get("anchor") or {})
    for key in ("char_start", "char_end", "block_start", "block_end"):
        if anchor.get(key) is not None:
            anchor[key] = int(anchor[key]) + offset
    data["anchor"] = anchor
    return OutlineNode.model_validate(data)


def _copy_images(src_ws: Path, dst_images: Path, *, rename_prefix: str = "") -> dict[str, str]:
    mapping: dict[str, str] = {}
    src_images = src_ws / "images"
    if not src_images.exists():
        return mapping
    dst_images.mkdir(parents=True, exist_ok=True)
    for src_file in src_images.iterdir():
        if not src_file.is_file():
            continue
        name = src_file.name
        dst_name = name
        if (dst_images / name).exists():
            dst_name = f"{rename_prefix}{name}"
        shutil.copy2(src_file, dst_images / dst_name)
        if dst_name != name:
            mapping[name] = dst_name
    return mapping


def merge_workspaces(
    target: Path,
    *,
    sources: list[tuple[Path, str]],
) -> Path:
    if len(sources) < 2:
        raise ValueError("merge_workspaces requires at least two sources")
    ws1_path, file1_name = sources[0]
    ws2_path, file2_name = sources[1]

    ws1 = OutputWorkspace.open_existing(ws1_path)
    ws2 = OutputWorkspace.open_existing(ws2_path)
    content1 = ws1.content_path.read_text(encoding="utf-8")
    content2 = ws2.content_path.read_text(encoding="utf-8")
    sep = _separator(file2_name)
    merged_content = content1 + sep + content2
    offset2 = len(content1) + len(sep)

    outline1 = OutlineTree.model_validate_json(ws1.outline_path.read_text(encoding="utf-8"))
    outline2 = OutlineTree.model_validate_json(ws2.outline_path.read_text(encoding="utf-8"))
    max_sort = max((n.sort_order for n in outline1.nodes), default=-1) + 1
    merged_nodes = list(outline1.nodes)
    for node in outline2.nodes:
        merged_nodes.append(_remap_node(node, prefix="m2:", offset=offset2, sort_shift=max_sort))

    merged_outline = OutlineTree(
        strategy=outline1.strategy,
        nodes=merged_nodes,
        derived_from=f"merged:{file1_name}+{file2_name}",
    )

    target.mkdir(parents=True, exist_ok=True)
    target_ws = OutputWorkspace.open_existing(target)
    target_ws.content_path.write_text(merged_content, encoding="utf-8")
    target_ws.outline_path.write_text(
        merged_outline.model_dump_json(indent=2),
        encoding="utf-8",
    )

    images_dir = target_ws.root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    _copy_images(ws1.root, images_dir)
    image_map = _copy_images(ws2.root, images_dir, rename_prefix="m2_")
    if image_map:
        head, tail = merged_content.split(sep, 1)
        for old, new in image_map.items():
            tail = tail.replace(f"images/{old}", f"images/{new}")
        merged_content = head + sep + tail
        target_ws.content_path.write_text(merged_content, encoding="utf-8")

    if ws1.manifest_path.exists():
        shutil.copy2(ws1.manifest_path, target_ws.manifest_path)

    return target_ws.root


def validate_merged_workspace(workspace: Path) -> None:
    ws = OutputWorkspace.open_existing(workspace)
    content = ws.content_path.read_text(encoding="utf-8")
    outline = OutlineTree.model_validate_json(ws.outline_path.read_text(encoding="utf-8"))
    node_ids = {node.node_id for node in outline.nodes}
    for node in outline.nodes:
        if node.parent_id and node.parent_id not in node_ids:
            raise ValueError(f"invalid parent_id: {node.parent_id}")
        if node.anchor.char_start is not None and node.anchor.char_end is not None:
            if not (0 <= node.anchor.char_start < node.anchor.char_end <= len(content)):
                raise ValueError(f"invalid anchor for {node.node_id}")
