from __future__ import annotations

from tender_insights.summary_loop.tasks import TASK_DEFINITIONS


def test_task_definitions_has_seven_steps_in_order():
    assert len(TASK_DEFINITIONS) == 7
    assert [t.current_task for t in TASK_DEFINITIONS] == [
        "get_tender_summary",
        "get_score_points",
        "get_disqualification_items",
        "get_tender_responds",
        "clearify_needs",
        "diagnosis_criteria",
        "generate_report",
    ]


def test_clarify_and_diagnosis_tasks_have_output_fields():
    clarify = TASK_DEFINITIONS[4]
    diagnosis = TASK_DEFINITIONS[5]
    report = TASK_DEFINITIONS[6]
    assert clarify.output_field == "needs_clarify"
    assert diagnosis.output_field == "diagnosis_criteria"
    assert report.output_field == "analysis_report"
    assert report.step_filename == "07_analysis_report.md"
