def test_package_importable():
    import tender_insights

    assert tender_insights.__version__ == "0.1.0"


def test_api_exports():
    from tender_insights.api import (
        prepare_workspaces,
        render_interpretation_report,
        run_interpret_job,
        run_template_job,
    )

    assert callable(prepare_workspaces)
    assert callable(run_interpret_job)
    assert callable(run_template_job)
    assert callable(render_interpretation_report)
