from __future__ import annotations

from tender_insights.bid_diagnose.tasks import TASK_DEFINITIONS
from tender_insights.common.diagnosis_prompts import DIAGNOSIS_CHECKLIST, DIAGNOSIS_SKILLS


def test_task_definitions_count_and_order():
    assert len(TASK_DEFINITIONS) == 3
    assert [t.current_task for t in TASK_DEFINITIONS] == [
        "import_diagnose",
        "diagnose_result",
        "update_diagnose",
    ]


def test_import_diagnose_reuses_shared_prompts():
    first = TASK_DEFINITIONS[0]
    assert first.task_skills == DIAGNOSIS_SKILLS
    assert first.output_requirement == DIAGNOSIS_CHECKLIST
    assert first.output_field == "import_diagnose"
