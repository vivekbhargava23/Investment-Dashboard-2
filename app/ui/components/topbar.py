import textwrap
import streamlit as st

PAGE_TITLES: dict[str, str] = {
    "overview": "Live Overview",
    "analytics": "Analytics & Risk",
    "performance": "Performance",
    "tax": "Tax Dashboard",
    "decision": "Decision Gates",
    "behaviour": "Behavioural Ledger",
    "lots": "Lot Ledger",
    "manage": "Manage Portfolio",
}

def render_topbar() -> None:
    current_page = st.session_state.get("current_page", "overview")
    title = PAGE_TITLES.get(current_page, "Investment Panel")
    
    # We use columns to allow a Streamlit button for the Refresh action
    # while keeping the layout consistent with the mockup.
    col1, col2 = st.columns([0.8, 0.2])
    
    with col1:
        st.markdown(textwrap.dedent(f"""
            <div class="topbar-left">
                <h1>{title}</h1>
                <div class="topbar-meta">USD/EUR 1.0786 · 14:14</div>
            </div>
        """).strip(), unsafe_allow_html=True)
    
    with col2:
        # Streamlit buttons have their own styling, but we'll try to match the mockup
        if st.button("Refresh", key="topbar_refresh", use_container_width=False):
            st.rerun()

    # Add a horizontal line to complete the topbar look if needed, 
    # though the .topbar class in CSS already has a border-bottom.
    # Since we split into columns, we might need a wrapper.
    st.markdown(
        '<div style="margin-top: -10px; border-bottom: 1px solid var(--border);"></div>',
        unsafe_allow_html=True
    )
