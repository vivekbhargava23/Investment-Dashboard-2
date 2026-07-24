import importlib
import logging
import os

import streamlit as st

from app.config import get_settings
from app.ui.components.sidebar import render_sidebar
from app.ui.components.topbar import render_topbar

logger = logging.getLogger(__name__)

# Load CSS
def load_css() -> None:
    # Use path relative to this file to ensure it's found regardless of where streamlit is run from
    css_path = os.path.join(os.path.dirname(__file__), "styles", "dark.css")
    try:
        with open(css_path) as f:
            # Inject CSS directly into the page
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"CSS file not found at {css_path}")

def render_placeholder() -> None:
    """Displays a placeholder for pages that aren't built yet."""
    page_id = st.session_state.get("current_page", "overview")
    st.title(page_id.replace("_", " ").title())
    st.info("Coming Soon")

def render_page_error(page_id: str, exc: Exception) -> None:
    """Surface a page crash instead of hiding it behind 'Coming Soon'.

    Always logs the traceback. In dev (app_env != "prod") the full exception is
    shown on the page; in prod the user sees a friendly message and the detail
    stays in the logs.
    """
    logger.exception("Page %r failed to render", page_id)
    if get_settings().app_env != "prod":
        st.error(f"Page '{page_id}' failed to load.")
        st.exception(exc)
    else:
        st.error(f"This page failed to load: {page_id}. Please try refreshing.")

def render_page() -> None:
    """Dynamically imports and renders the current page.

    "Coming Soon" is reserved for pages that genuinely have no render() (the
    not-built case: missing module file or no render attribute). A page whose
    import or render() *raises* is a real bug — it gets a logged, visible error
    surface, never the misleading placeholder.
    """
    page_id = st.session_state.get("current_page", "overview")

    # A page is either a single module file (pages/<id>.py) or a package
    # directory with an __init__.py (pages/<id>/__init__.py that re-exports
    # render). Not built: neither exists on disk.
    module_path = os.path.join("app", "ui", "pages", f"{page_id}.py")
    package_path = os.path.join("app", "ui", "pages", page_id, "__init__.py")
    if not os.path.exists(module_path) and not os.path.exists(package_path):
        render_placeholder()
        return

    try:
        module = importlib.import_module(f"app.ui.pages.{page_id}")
    except Exception as exc:
        # Import raised — a real bug, not a not-built page.
        render_page_error(page_id, exc)
        return

    # Not built: module exists but has no render() entry point.
    render_fn = getattr(module, "render", None)
    if render_fn is None:
        render_placeholder()
        return

    try:
        render_fn()
    except Exception as exc:
        render_page_error(page_id, exc)

def main() -> None:
    """Streamlit entry point: configure the page and render the active view.

    Kept inside a function (rather than at module level) so the router helpers
    above can be imported and unit-tested without triggering Streamlit's
    page-render side effects. Streamlit runs this script with __name__ ==
    "__main__", so the guard below fires under `streamlit run`.
    """
    st.set_page_config(
        page_title="Investment Panel",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    load_css()

    # Sync session state with query params
    query_params = st.query_params
    if "page" in query_params:
        st.session_state.current_page = query_params["page"]

    if "current_page" not in st.session_state:
        st.session_state.current_page = "overview"

    # Main Layout
    col_sidebar, col_main = st.columns([0.18, 0.82], gap="small")

    with col_sidebar:
        render_sidebar()

    with col_main:
        render_topbar()
        # Execute the current page's render logic
        render_page()


if __name__ == "__main__":
    main()
