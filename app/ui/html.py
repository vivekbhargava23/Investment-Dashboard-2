"""HTML rendering helper for Streamlit pages.

Markdown's parser treats any line indented 4+ spaces as a code block. HTML
strings built inside indented f-strings inherit that leading whitespace, causing
the raw tags to render as visible text instead of HTML. This module is the
single exit point for all HTML emitted via st.markdown. It applies
textwrap.dedent + str.strip before every call, making the leading-whitespace
bug structurally impossible.
"""
from textwrap import dedent

import streamlit as st


def render_html(html: str) -> None:
    st.markdown(dedent(html).strip(), unsafe_allow_html=True)
