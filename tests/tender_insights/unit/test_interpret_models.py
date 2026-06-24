from tender_insights.interpret.models import (
    BidRiskItem,
    DirectoryRequirement,
    DisqualificationItem,
    InterpretationFile,
    InterpretationOverview,
    ScoringCriterionNode,
    ScoringItem,
    Severity,
)


def _overview() -> InterpretationOverview:
    return InterpretationOverview(
        summary="概要",
        disqualification_summary="废标概要",
        scoring_summary="得分概要",
        bid_risk_summary="风险概要",
        directory_summary="目录概要",
    )


def test_interpretation_file_roundtrip() -> None:
    payload = InterpretationFile(
        source_workspace="/tmp/ws",
        overview=_overview(),
        disqualification_items=[
            DisqualificationItem(
                id="dq-001",
                title="未递交文件",
                summary="未按时递交",
                trigger_condition="逾期递交",
                source_excerpt="逾期递交作废",
                section_path=["须知"],
                confidence=0.9,
            )
        ],
        scoring_items=[
            ScoringItem(
                id="sc-001",
                title="技术分",
                summary="技术评分",
                max_score=30.0,
                weight="30%",
                criteria="方案完整性",
                source_excerpt="技术30分",
                section_path=["评标"],
                confidence=0.85,
            )
        ],
        bid_risk_items=[
            BidRiskItem(
                id="br-001",
                title="资质风险",
                summary="资质不足",
                severity=Severity.high,
                risk_category="资质",
                source_excerpt="须具备一级资质",
                section_path=["须知"],
                confidence=0.8,
            )
        ],
        directory_requirements=[
            DirectoryRequirement(
                id="dr-001",
                title="文件组成",
                required_sections=["投标函", "资质证明"],
                mandatory=True,
                source_excerpt="投标文件包括...",
                section_path=["格式"],
                confidence=0.9,
            )
        ],
    )
    restored = InterpretationFile.model_validate_json(payload.model_dump_json())
    assert restored.disqualification_items[0].id == "dq-001"
    assert restored.scoring_items[0].max_score == 30.0
    assert restored.overview.summary == "概要"
    assert restored.schema_version == "1.2"


def test_scoring_item_with_children_roundtrip() -> None:
    child = ScoringCriterionNode(
        id="sc-001-01",
        title="方案完整性",
        max_score=10.0,
        score_range="0-10",
        criteria="方案覆盖全部要求得10分",
        source_excerpt="原文",
    )
    payload = InterpretationFile(
        source_workspace="/tmp/ws",
        overview=_overview(),
        scoring_items=[
            ScoringItem(
                id="sc-001",
                title="技术部分",
                summary="技术评分",
                max_score=40.0,
                weight="40%",
                criteria="大类说明",
                children=[child],
                source_excerpt="技术40分",
                section_path=["第二章 响应人须知"],
                confidence=0.9,
            )
        ],
    )
    restored = InterpretationFile.model_validate_json(payload.model_dump_json())
    assert restored.schema_version == "1.2"
    assert len(restored.scoring_items[0].children) == 1
    assert restored.scoring_items[0].children[0].score_range == "0-10"


def test_directory_requirement_inferred_default_false() -> None:
    dr = DirectoryRequirement(
        id="dr-001",
        title="组成",
        required_sections=["投标函"],
        mandatory=True,
        source_excerpt="x",
        section_path=[],
        confidence=0.8,
    )
    assert dr.inferred is False
