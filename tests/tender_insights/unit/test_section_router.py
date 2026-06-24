from doc_chunk.models.outline import OutlineNode, OutlineTree

from tender_insights.common.section_router import SectionRouter


def test_route_nodes_by_keyword() -> None:
    tree = OutlineTree(
        nodes=[
            OutlineNode(node_id="n1", title="投标人须知", level=1, parent_id=None, sort_order=0),
            OutlineNode(node_id="n2", title="评标办法", level=1, parent_id=None, sort_order=1),
            OutlineNode(node_id="n3", title="附件：承诺书", level=1, parent_id=None, sort_order=2),
        ]
    )
    rules = {
        "disqualification": {"keywords": ["须知", "废标"]},
        "scoring": {"keywords": ["评标"]},
        "template": {"keywords": ["附件", "承诺书"]},
    }
    router = SectionRouter(rules)
    dq = router.match_nodes(tree, "disqualification")
    assert [n.node_id for n in dq] == ["n1"]
    sc = router.match_nodes(tree, "scoring")
    assert [n.node_id for n in sc] == ["n2"]
