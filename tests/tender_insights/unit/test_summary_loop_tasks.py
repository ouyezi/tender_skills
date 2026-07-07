from __future__ import annotations

from tender_insights.summary_loop.tasks import TASK_DEFINITIONS


def test_task_definitions_has_five_steps_in_order():
    assert len(TASK_DEFINITIONS) == 5
    assert [t.current_task for t in TASK_DEFINITIONS] == [
        "get_tender_summary",
        "get_score_points",
        "get_disqualification_items",
        "get_tender_responds",
        "generate_report",
    ]


def test_generate_report_has_no_output_field():
    report_task = TASK_DEFINITIONS[-1]
    assert report_task.current_task == "generate_report"
    assert report_task.output_field is None
    assert report_task.step_filename == "05_report.md"
