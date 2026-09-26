from pathlib import Path
from cocli.utils.terminal_preview import render_html_for_terminal


def test_render_html_snippet_for_terminal():
    snippet = """
    <div style="background-color:#f7f4ec; padding:16px;">
        <strong>Chip Slaughter:</strong> "Taxes can erode retirement income."
    </div>
    <p>Visit <a href="https://example.com">here</a>.</p>
    """
    res = render_html_for_terminal(snippet, width=60)
    assert res is not None
    assert "Chip Slaughter" in res
    assert "Taxes can erode retirement income" in res
    assert "<div" not in res
    assert "style=" not in res


def test_render_html_file_for_terminal(tmp_path: Path):
    html_file = tmp_path / "test.html"
    html_file.write_text("<h3>Header</h3><p>Hello world</p>", encoding="utf-8")

    res = render_html_for_terminal(html_file, width=60)
    assert res is not None
    assert "Header" in res
    assert "Hello world" in res
    assert "<h3" not in res


def test_render_html_missing_file(tmp_path: Path):
    missing_file = tmp_path / "nonexistent.html"
    res = render_html_for_terminal(missing_file)
    assert res is None
