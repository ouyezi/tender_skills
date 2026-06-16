from __future__ import annotations

import json

from doc_chunk.models.chunk import ChunkBlock


def _block_to_v1_dict(
    block: ChunkBlock,
    image_ref_to_asset_id: dict[str, str] | None,
) -> dict:
    data = block.model_dump(mode="json", exclude_none=True)
    if block.type == "image" and block.image_ref and image_ref_to_asset_id:
        asset_id = image_ref_to_asset_id.get(block.image_ref)
        if asset_id:
            data["asset_id"] = asset_id
    return data


def blocks_to_v1_json(
    blocks: list[ChunkBlock],
    *,
    image_ref_to_asset_id: dict[str, str] | None = None,
) -> str:
    payload = {
        "format": "blocks_v1",
        "blocks": [_block_to_v1_dict(block, image_ref_to_asset_id) for block in blocks],
    }
    return json.dumps(payload, ensure_ascii=False)
