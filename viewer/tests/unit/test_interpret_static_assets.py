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
