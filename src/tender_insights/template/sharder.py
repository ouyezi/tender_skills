from __future__ import annotations

from typing import Literal

from doc_chunk.models.outline import OutlineNode, OutlineTree

from tender_insights.common.section_slice import node_char_range
from tender_insights.config import InsightsConfig
from tender_insights.template.boundary import _HEADING_RE
from tender_insights.template.models import TemplateShard


def _section_path(node_id: str, outline: OutlineTree) -> list[str]:
    node_map = {n.node_id: n for n in outline.nodes}
    chain: list[str] = []
    cur = node_map.get(node_id)
    while cur:
        chain.append(cur.title)
        cur = node_map.get(cur.parent_id) if cur.parent_id else None
    return list(reversed(chain))


def _shard(
    shard_id: str,
    strategy: Literal["whole_doc", "outline_l1", "outline_child", "heading", "char"],
    section_path: list[str],
    char_start: int,
    char_end: int,
) -> TemplateShard:
    return TemplateShard(
        shard_id=shard_id,
        strategy=strategy,
        section_path=section_path,
        char_start=char_start,
        char_end=char_end,
        char_count=char_end - char_start,
    )


def _char_shards(
    content_md: str,
    config: InsightsConfig,
    *,
    section_path: list[str],
    start: int,
    end: int,
) -> list[TemplateShard]:
    max_chars = config.template_shard_max_chars
    overlap = config.template_char_chunk_overlap
    step = max(1, max_chars - overlap)
    shards: list[TemplateShard] = []
    pos = start
    while pos < end:
        chunk_end = min(pos + max_chars, end)
        shards.append(_shard("", "char", section_path, pos, chunk_end))
        if chunk_end >= end:
            break
        pos += step
    return shards


def _heading_shards(
    content_md: str,
    config: InsightsConfig,
    *,
    section_path: list[str],
    start: int,
    end: int,
) -> list[TemplateShard]:
    matches = [
        match
        for match in _HEADING_RE.finditer(content_md)
        if start <= match.start() < end and 1 <= len(match.group(1)) <= 4
    ]
    if not matches:
        return _char_shards(content_md, config, section_path=section_path, start=start, end=end)

    raw: list[TemplateShard] = []
    if matches[0].start() > start:
        pre_start, pre_end = start, matches[0].start()
        if pre_end - pre_start > config.template_shard_max_chars:
            raw.extend(
                _char_shards(content_md, config, section_path=section_path, start=pre_start, end=pre_end)
            )
        else:
            raw.append(_shard("", "heading", section_path, pre_start, pre_end))

    for idx, match in enumerate(matches):
        h_start = match.start()
        h_end = matches[idx + 1].start() if idx + 1 < len(matches) else end
        heading_title = match.group(2).strip()
        path = section_path + [heading_title]
        if h_end - h_start > config.template_shard_max_chars:
            raw.extend(_char_shards(content_md, config, section_path=path, start=h_start, end=h_end))
        else:
            raw.append(_shard("", "heading", path, h_start, h_end))
    return raw


def _refine_shard(
    content_md: str,
    outline: OutlineTree,
    node: OutlineNode,
    start: int,
    end: int,
    section_path: list[str],
    config: InsightsConfig,
    *,
    strategy: Literal["outline_l1", "outline_child"] = "outline_l1",
) -> list[TemplateShard]:
    if end - start <= config.template_shard_max_chars:
        return [_shard("", strategy, section_path, start, end)]

    children = sorted(
        [child for child in outline.nodes if child.parent_id == node.node_id],
        key=lambda child: child.anchor.char_start if child.anchor else 0,
    )
    if children:
        raw: list[TemplateShard] = []
        for child in children:
            child_start, child_end = node_char_range(content_md, outline, child.node_id)
            child_path = _section_path(child.node_id, outline)
            raw.extend(
                _refine_shard(
                    content_md,
                    outline,
                    child,
                    child_start,
                    child_end,
                    child_path,
                    config,
                    strategy="outline_child",
                )
            )
        return raw

    return _heading_shards(content_md, config, section_path=section_path, start=start, end=end)


def _reindex_shards(shards: list[TemplateShard]) -> list[TemplateShard]:
    return [
        shard.model_copy(update={"shard_id": f"shard-{index:03d}"})
        for index, shard in enumerate(shards, start=1)
    ]


def build_template_shards(
    content_md: str,
    outline: OutlineTree,
    *,
    config: InsightsConfig,
) -> list[TemplateShard]:
    n = len(content_md)
    if n <= config.template_whole_doc_max_chars:
        return [_shard("shard-001", "whole_doc", [], 0, n)]

    l1_nodes = sorted(
        [node for node in outline.nodes if node.level == 1],
        key=lambda node: node.anchor.char_start if node.anchor else 0,
    )
    if not l1_nodes:
        return _reindex_shards(
            _char_shards(content_md, config, section_path=[], start=0, end=n)
        )

    raw: list[TemplateShard] = []
    for node in l1_nodes:
        start, end = node_char_range(content_md, outline, node.node_id)
        path = _section_path(node.node_id, outline)
        raw.extend(_refine_shard(content_md, outline, node, start, end, path, config))
    return _reindex_shards(raw)
