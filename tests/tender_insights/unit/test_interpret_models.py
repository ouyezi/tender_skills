from tender_insights.interpret.models import (
    BidRiskItem,
    DirectoryRequirement,
    DisqualificationItem,
    InterpretationFile,
    ScoringItem,
    Severity,
)


def test_interpretation_file_roundtrip() -> None:
    payload = InterpretationFile(
        source_workspace="/tmp/ws",
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
