from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "viewer" / "static"


def test_interpret_js_renders_scoring_children() -> None:
    js = (STATIC / "interpret.js").read_text(encoding="utf-8")
    assert "renderScoringChildren" in js
    assert "item.children" in js
    assert "score_range" in js


def test_style_has_scoring_child_classes() -> None:
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".scoring-child" in css
    assert ".scoring-children" in css


def test_interpret_js_renders_directory_structure() -> None:
    js = (STATIC / "interpret.js").read_text(encoding="utf-8")
    assert "renderStructureTree" in js
    assert "item.inferred" in js


def test_interpret_js_renders_overview() -> None:
    js = (STATIC / "interpret.js").read_text(encoding="utf-8")
    assert "renderOverview" in js


def test_interpret_html_has_overview_panel() -> None:
    html = (STATIC / "interpret.html").read_text(encoding="utf-8")
    assert 'id="overview-panel"' in html


def test_interpret_html_has_brief_button() -> None:
    html = (STATIC / "interpret.html").read_text(encoding="utf-8")
    assert 'id="brief-btn"' in html
    assert "提取概要" in html


def test_interpret_js_has_brief_tab() -> None:
    js = (STATIC / "interpret.js").read_text(encoding="utf-8")
    assert 'key: "brief"' in js
    assert "renderBrief" in js
    assert "upload?job_kind=brief" in js
