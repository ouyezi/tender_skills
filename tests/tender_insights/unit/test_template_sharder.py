from doc_chunk.models.outline import Anchor, OutlineNode, OutlineTree

from tender_insights.config import InsightsConfig
from tender_insights.template.sharder import build_template_shards

CONTENT = "# 第一章\n\n" + ("正文 " * 100)

CHAPTER4 = (
    "# 第四章参选文件格式\n\n"
    "## 授权书\n\n授权正文\n\n"
    "## 声明函\n\n声明正文\n"
)
LONG_PREFIX = "x" * 30_000


def test_sharder_whole_doc_when_small() -> None:
    outline = OutlineTree(
        nodes=[
            OutlineNode(node_id="n1", title="第一章", level=1, parent_id=None, sort_order=0),
        ]
    )
    cfg = InsightsConfig(template_whole_doc_max_chars=100_000)
    shards = build_template_shards(CONTENT, outline, config=cfg)
    assert len(shards) == 1
    assert shards[0].strategy == "whole_doc"
    assert shards[0].char_start == 0
    assert shards[0].char_end == len(CONTENT)


def test_sharder_splits_by_heading_when_l1_too_large() -> None:
    content = LONG_PREFIX + CHAPTER4
    start = len(LONG_PREFIX)
    outline = OutlineTree(
        nodes=[
            OutlineNode(
                node_id="n4",
                title="第四章参选文件格式",
                level=1,
                parent_id=None,
                sort_order=0,
                anchor=Anchor(char_start=start, char_end=len(content)),
            ),
        ]
    )
    cfg = InsightsConfig(template_whole_doc_max_chars=1000, template_shard_max_chars=5000)
    shards = build_template_shards(content, outline, config=cfg)
    strategies = {shard.strategy for shard in shards}
    assert "heading" in strategies or "outline_l1" in strategies
    assert (
        sum(
            1
            for shard in shards
            if "授权" in "".join(shard.section_path) or shard.char_start >= start
        )
        >= 1
    )
