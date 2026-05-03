# app/ui/CLAUDE.md

Streamlit UI layer. Render only — no domain logic.

## HTML rendering rule

Any helper or page that emits HTML for `st.markdown` must use `render_html()` from `app/ui/render.py`. This is the *only* place in the codebase where `unsafe_allow_html=True` is set. Never call `st.markdown(..., unsafe_allow_html=True)` directly. The helper handles dedent + strip so leading-whitespace markdown-as-code-block bugs are impossible by construction.
