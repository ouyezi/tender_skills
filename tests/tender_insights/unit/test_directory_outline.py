from tender_insights.interpret.directory_outline import build_directory_outline
from tender_insights.interpret.models import DirectoryRequirement, DirectoryStructureNode


def test_build_directory_outline_from_structure() -> None:
    reqs = [
        DirectoryRequirement(
            id="dr-1",
            title="组成",
            required_sections=[],
            mandatory=True,
            structure=[
                DirectoryStructureNode(order=1, number="一", title="投标函", mandatory=True),
            ],
            source_excerpt="x",
            section_path=["格式"],
            confidence=0.9,
        )
    ]
    outline = build_directory_outline(reqs)
    assert len(outline.nodes) == 1
    assert outline.nodes[0].title == "投标函"
    assert outline.confidence == 0.85


def test_build_directory_outline_from_flat_sections() -> None:
    reqs = [
        DirectoryRequirement(
            id="dr-1",
            title="组成",
            required_sections=["投标函", "资质"],
            mandatory=True,
            source_excerpt="x",
            section_path=["格式"],
            confidence=0.9,
        )
    ]
    outline = build_directory_outline(reqs)
    assert len(outline.nodes) == 2
    assert outline.confidence == 0.6


def test_build_directory_outline_recurses_children() -> None:
    reqs = [
        DirectoryRequirement(
            id="dr-1",
            title="组成",
            required_sections=[],
            mandatory=True,
            inferred=False,
            structure=[
                DirectoryStructureNode(
                    order=1,
                    number="一",
                    title="商务文件",
                    mandatory=True,
                    children=[
                        DirectoryStructureNode(order=1, title="投标函", mandatory=True),
                    ],
                )
            ],
            source_excerpt="x",
            section_path=["格式"],
            confidence=0.9,
        )
    ]
    outline = build_directory_outline(reqs)
    assert len(outline.nodes) == 2
    assert outline.nodes[0].level == 1
    assert outline.nodes[1].level == 2
    assert outline.nodes[1].title == "投标函"


def test_build_directory_outline_lower_confidence_for_inferred() -> None:
    reqs = [
        DirectoryRequirement(
            id="dr-1",
            title="推断投标文件组成",
            required_sections=[],
            mandatory=True,
            inferred=True,
            structure=[DirectoryStructureNode(order=1, title="投标函", mandatory=True)],
            source_excerpt="",
            section_path=[],
            confidence=0.65,
        )
    ]
    outline = build_directory_outline(reqs)
    assert outline.confidence == 0.55
