from __future__ import annotations

from cocli.utils.html_to_text import html_to_text


def test_strips_tags_and_keeps_line_breaks() -> None:
    html = "<p>Hi Bob,</p><p>Here is a <b>table</b>.</p><div>Line one<br>Line two</div>"
    text = html_to_text(html)
    assert "Hi Bob," in text
    assert "Here is a table" in text
    assert "Line one" in text
    assert "Line two" in text
    assert "<" not in text


def test_strips_style_and_script_content() -> None:
    html = "<style>.foo { color: red; }</style><script>alert(1)</script><p>Real content</p>"
    text = html_to_text(html)
    assert "color" not in text
    assert "alert" not in text
    assert text == "Real content"
