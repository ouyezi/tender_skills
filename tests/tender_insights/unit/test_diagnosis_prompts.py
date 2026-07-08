from __future__ import annotations

from tender_insights.common.diagnosis_prompts import DIAGNOSIS_CHECKLIST, DIAGNOSIS_SKILLS


def test_diagnosis_skills_non_empty():
    assert "诊断" in DIAGNOSIS_SKILLS
    assert len(DIAGNOSIS_SKILLS) > 50


def test_diagnosis_checklist_contains_table_header():
    assert "| **序号** | **诊断要点** |" in DIAGNOSIS_CHECKLIST
