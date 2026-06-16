from doc_chunk.models.outline import OutlineNode, OutlineTree

from tender_insights.template.detector import detect_template_nodes


def test_detect_template_nodes_by_keyword() -> None:
    tree = OutlineTree(
        nodes=[
            OutlineNode(node_id="n1", title="投标人须知", level=1, parent_id=None, sort_order=0),
            OutlineNode(node_id="n2", title="附件：承诺书格式", level=1, parent_id=None, sort_order=1),
            OutlineNode(node_id="n3", title="授权委托书", level=2, parent_id="n2", sort_order=2),
        ]
    )
    hits = detect_template_nodes(tree)
    assert {h.node_id for h in hits} == {"n2", "n3"}
