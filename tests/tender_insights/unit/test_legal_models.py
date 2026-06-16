from tender_insights.interpret.models import Severity
from tender_insights.legal.models import (
    LegalReviewFile,
    LegalRiskItem,
    PendingConfirmation,
)


def test_legal_review_file_roundtrip() -> None:
    payload = LegalReviewFile(
        source_workspace="/tmp/ws",
        risk_items=[
            LegalRiskItem(
                id="lr-001",
                description="付款周期过长",
                clause_excerpt="甲方应在验收后180日内付款",
                risk_type="付款",
                severity=Severity.high,
                section_path=["合同", "付款条款"],
                confidence=0.9,
            )
        ],
        pending_confirmations=[
            PendingConfirmation(
                id="pc-001",
                description="知识产权归属不明确",
                confirm_with="甲方法务",
                suggested_question="请明确软件开发成果的知识产权归属",
                section_path=["通用条款"],
                confidence=0.85,
            )
        ],
    )
    restored = LegalReviewFile.model_validate_json(payload.model_dump_json())
    assert restored.risk_items[0].id == "lr-001"
    assert restored.risk_items[0].severity == Severity.high
    assert restored.pending_confirmations[0].confirm_with == "甲方法务"
