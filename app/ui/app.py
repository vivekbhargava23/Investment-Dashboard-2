import streamlit as st

import app.ui.pages.analytics as analytics
import app.ui.pages.behaviour as behaviour
import app.ui.pages.decision as decision
import app.ui.pages.lots as lots
import app.ui.pages.manage as manage
import app.ui.pages.overview as overview
import app.ui.pages.performance as performance
import app.ui.pages.tax as tax
from app.ui.components.sidebar import render_sidebar
from app.ui.components.topbar import render_topbar

# Page Configuration
st.set_page_config(
    page_title="Investment Panel",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Load CSS
def load_css() -> None:
    try:
        with open("app/ui/styles/dark.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error("CSS file not found at app/ui/styles/dark.css")

load_css()

# Routing Logic
PAGE_REGISTRY = {
    "overview": overview.render,
    "analytics": analytics.render,
    "performance": performance.render,
    "tax": tax.render,
    "decision": decision.render,
    "behaviour": behaviour.render,
    "lots": lots.render,
    "manage": manage.render,
}

# Sync session state with query params
query_params = st.query_params
if "page" in query_params:
    st.session_state.current_page = query_params["page"]

if "current_page" not in st.session_state:
    st.session_state.current_page = "overview"

# Main Layout
# We use a custom flex container to match the mockup's sidebar/main split.
# Since Streamlit columns have fixed gaps and padding, we render the skeleton as HTML.

# Real implementation using Streamlit columns but hiding the gaps
col_sidebar, col_main = st.columns([0.18, 0.82], gap="small")

with col_sidebar:
    st.markdown(render_sidebar(), unsafe_allow_html=True)

with col_main:
    render_topbar()
    # Execute the current page's render function
    page_func = PAGE_REGISTRY.get(st.session_state.current_page, overview.render)
    page_func()
