import importlib
import os

import streamlit as st

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
    # Use path relative to this file to ensure it's found regardless of where streamlit is run from
    css_path = os.path.join(os.path.dirname(__file__), "styles", "dark.css")
    try:
        with open(css_path) as f:
            # Inject CSS directly into the page
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"CSS file not found at {css_path}")

load_css()

def render_placeholder() -> None:
    """Displays a placeholder for pages that aren't built yet."""
    page_id = st.session_state.get("current_page", "overview")
    st.title(page_id.replace("_", " ").title())
    st.info("Coming Soon")

def render_page() -> None:
    """Dynamically imports and renders the current page."""
    page_id = st.session_state.get("current_page", "overview")
    
    # Path to the page module file
    page_path = os.path.join("app", "ui", "pages", f"{page_id}.py")
    
    if os.path.exists(page_path):
        try:
            # Dynamically import the page module
            module = importlib.import_module(f"app.ui.pages.{page_id}")
            if hasattr(module, "render"):
                module.render()
                return
        except Exception:
            # If import fails or render is missing, fallback to placeholder
            pass
            
    render_placeholder()

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
    # Execute the current page's render logic
    render_page()
