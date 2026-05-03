import streamlit as st

import app.ui.pages.overview as overview
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

def render_placeholder() -> None:
    st.info("This page is coming soon.")

# Routing Logic
# For now, we only wire the overview page. 
# Other pages will be imported and added as their tickets are implemented.
PAGE_REGISTRY = {
    "overview": overview.render,
}

# Sync session state with query params
query_params = st.query_params
if "page" in query_params:
    st.session_state.current_page = query_params["page"]

if "current_page" not in st.session_state:
    st.session_state.current_page = "overview"

# Main Layout
col_sidebar, col_main = st.columns([0.18, 0.82], gap="small")

with col_sidebar:
    st.markdown(render_sidebar(), unsafe_allow_html=True)

with col_main:
    render_topbar()
    # Execute the current page's render function
    page_func = PAGE_REGISTRY.get(st.session_state.current_page, render_placeholder)
    page_func()
