import json

from doc_chunk.convert.blocks_v1 import blocks_to_v1_json
from doc_chunk.models.chunk import ChunkBlock


def test_blocks_to_v1_json_format() -> None:
    payload = blocks_to_v1_json(
        [
            ChunkBlock(type="paragraph", text="hello"),
            ChunkBlock(type="image", image_ref="images/a.png"),
        ]
    )
    data = json.loads(payload)
    assert data["format"] == "blocks_v1"
    assert data["blocks"][0]["type"] == "paragraph"
    assert data["blocks"][1]["image_ref"] == "images/a.png"
