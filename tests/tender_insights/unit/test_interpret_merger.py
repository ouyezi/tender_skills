from tender_insights.interpret.merger import (
    dedupe_by_title,
    merge_scoring_items,
    normalize_directory_requirements,
)
from tender_insights.interpret.models import (
    DirectoryRequirement,
    DirectoryStructureNode,
    DisqualificationItem,
    ScoringCriterionNode,
    ScoringItem,
)


def test_dedupe_prefers_longer_excerpt_on_tie() -> None:
    items = [
        DisqualificationItem(
            id="dq-001", title="逾期", summary="a", trigger_condition="t",
            source_excerpt="short", section_path=[], confidence=0.9,
        ),
        DisqualificationItem(
            id="dq-002", title="逾期", summary="b", trigger_condition="t",
            source_excerpt="much longer excerpt", section_path=[], confidence=0.9,
        ),
    ]
    out = dedupe_by_title(items)
    assert len(out) == 1
    assert out[0].source_excerpt == "much longer excerpt"


def test_dedupe_by_title_keeps_higher_confidence() -> None:
    items = [
        DisqualificationItem(
            id="dq-001", title="逾期", summary="a", trigger_condition="t",
            source_excerpt="x", section_path=[], confidence=0.5,
        ),
        DisqualificationItem(
            id="dq-002", title="逾期", summary="b", trigger_condition="t",
            source_excerpt="y", section_path=[], confidence=0.9,
        ),
    ]
    out = dedupe_by_title(items)
    assert len(out) == 1
    assert out[0].confidence == 0.9


def _scoring(
    title: str,
    *,
    max_score: float | None = None,
    children: list[ScoringCriterionNode] | None = None,
) -> ScoringItem:
    return ScoringItem(
        id="sc-x",
        title=title,
        summary="s",
        max_score=max_score,
        criteria="c",
        children=children or [],
        source_excerpt="ex",
        section_path=[],
        confidence=0.9,
    )


def test_merge_scoring_items_unions_children_same_parent() -> None:
    items = [
        _scoring(
            "技术部分",
            max_score=40.0,
            children=[
                ScoringCriterionNode(
                    id="sc-001-01", title="方案完整性", criteria="a", source_excerpt="a"
                )
            ],
        ),
        _scoring(
            "技术部分",
            max_score=40.0,
            children=[
                ScoringCriterionNode(
                    id="sc-001-02", title="人员配置", criteria="b", source_excerpt="b"
                )
            ],
        ),
    ]
    out = merge_scoring_items(items)
    assert len(out) == 1
    titles = {c.title for c in out[0].children}
    assert titles == {"方案完整性", "人员配置"}


def test_merge_scoring_items_prefers_longer_child_criteria() -> None:
    items = [
        _scoring(
            "商务部分",
            children=[
                ScoringCriterionNode(
                    id="1", title="报价", criteria="短", source_excerpt="x"
                )
            ],
        ),
        _scoring(
            "商务部分",
            children=[
                ScoringCriterionNode(
                    id="2", title="报价", criteria="更长的评分细则说明", source_excerpt="y"
                )
            ],
        ),
    ]
    out = merge_scoring_items(items)
    assert len(out[0].children) == 1
    assert out[0].children[0].criteria == "更长的评分细则说明"


def test_normalize_directory_keeps_explicit_structure() -> None:
    explicit = DirectoryRequirement(
        id="dr-1",
        title="投标文件组成",
        required_sections=[],
        mandatory=True,
        inferred=False,
        structure=[DirectoryStructureNode(order=1, title="投标函", mandatory=True)],
        source_excerpt="x",
        section_path=["格式"],
        confidence=0.9,
    )
    out = normalize_directory_requirements([explicit])
    assert len(out) == 1
    assert out[0].inferred is False


def test_normalize_directory_merges_scattered_into_inferred() -> None:
    scattered = [
        DirectoryRequirement(
            id="dr-1",
            title="材料A",
            required_sections=["投标函"],
            mandatory=True,
            source_excerpt="a",
            section_path=[],
            confidence=0.7,
        ),
        DirectoryRequirement(
            id="dr-2",
            title="材料B",
            required_sections=["资质证明"],
            mandatory=True,
            source_excerpt="b",
            section_path=[],
            confidence=0.6,
        ),
    ]
    out = normalize_directory_requirements(scattered)
    assert len(out) == 1
    assert out[0].inferred is True
    assert out[0].title == "推断投标文件组成"
    titles = [n.title for n in out[0].structure]
    assert titles == ["投标函", "资质证明"]
