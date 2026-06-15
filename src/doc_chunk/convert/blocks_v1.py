from __future__ import annotations

import json

from doc_chunk.models.chunk import ChunkBlock


def blocks_to_v1_json(blocks: list[ChunkBlock]) -> str:
    payload = {
        "format": "blocks_v1",
        "blocks": [b.model_dump(mode="json", exclude_none=True) for b in blocks],
    }
    return json.dumps(payload, ensure_ascii=False)
