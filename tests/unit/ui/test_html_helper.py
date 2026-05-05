"""Tests for app.ui.html.render_html helper."""
from unittest.mock import patch


def test_render_html_strips_leading_whitespace() -> None:
    indented = """
        <div>hello</div>
    """
    with patch("streamlit.markdown") as mock_md:
        from app.ui.render import render_html

        render_html(indented)
        call_args = mock_md.call_args
        rendered = call_args[0][0]
        assert rendered[0] == "<", f"Expected '<' at position 0, got: {rendered!r}"


def test_render_html_preserves_internal_structure() -> None:
    html = """
        <table>
            <tr><td>cell</td></tr>
        </table>
    """
    with patch("streamlit.markdown") as mock_md:
        from app.ui.render import render_html

        render_html(html)
        rendered = mock_md.call_args[0][0]
        assert "<table>" in rendered
        assert "<tr>" in rendered
        assert "<td>cell</td>" in rendered


def test_render_html_empty_string() -> None:
    with patch("streamlit.markdown") as mock_md:
        from app.ui.render import render_html

        render_html("")
        mock_md.assert_called_once()
        rendered = mock_md.call_args[0][0]
        assert rendered == ""


def test_render_html_uses_unsafe_allow_html() -> None:
    with patch("streamlit.markdown") as mock_md:
        from app.ui.render import render_html

        render_html("<p>x</p>")
        call_kwargs = mock_md.call_args[1]
        assert call_kwargs.get("unsafe_allow_html") is True
