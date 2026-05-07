import textwrap
from datetime import date
from typing import Any

import streamlit as st

NAV_ITEMS: list[dict[str, Any]] = [
    {"id": "overview",    "label": "Live Overview",      "icon": "◉", "badge": None},
    {"id": "manage",      "label": "Manage Portfolio",   "icon": "⚙", "badge": None},
    {"id": "tax",         "label": "Tax Dashboard",      "icon": "§", "badge": None},
    {"id": "research",    "label": "Research",           "icon": "📈", "badge": None},
    {"id": "simulator",   "label": "Sell Simulator",     "icon": "⚡", "badge": None},
    {"id": "performance", "label": "Performance",        "icon": "↗", "badge": None},
    {
        "id": "analytics",
        "label": "Analytics & Risk",
        "icon": "⬡",
        "badge": {"text": "new", "color": "amber"}
    },
    {
        "id": "decision",
        "label": "Decision Gates",
        "icon": "▲",
        "badge": {"text": "3 flags", "color": ""}
    },
    {"id": "behaviour",   "label": "Behavioural Ledger", "icon": "◎", "badge": None},
    {"id": "lots",        "label": "Lot Ledger",         "icon": "≡", "badge": None},
]

def render_sidebar() -> str:
    """
    Returns the HTML string for the sidebar.
    The routing is handled via query params in the <a> tags.
    """
    current_page = st.session_state.get("current_page", "overview")
    
    # Brand block
    brand_html = textwrap.dedent("""
        <div class="sidebar-logo">
            <div class="mark">
                <div class="icon">📈</div>
                <div class="name">Investment Panel</div>
            </div>
            <div class="sub">Scalable Capital · DE</div>
        </div>
    """).strip()
    
    # Nav items
    nav_html = '<div class="sidebar-nav">'
    
    # Portfolio section
    nav_html += '<div class="nav-section-label">Portfolio</div>'
    for item in NAV_ITEMS:
        active_class = "active" if current_page == item["id"] else ""
        badge_html = ""
        if item["badge"]:
            badge_class = f"nav-badge {item['badge']['color']}"
            badge_html = f'<span class="{badge_class}">{item["badge"]["text"]}</span>'
        
        nav_html += textwrap.dedent(f"""
            <a href="/?page={item['id']}" target="_self" class="nav-item-link {active_class}">
                <span class="nav-icon">{item['icon']}</span>
                <span>{item['label']}</span>
                {badge_html}
            </a>
        """).strip()
    
    nav_html += '</div>' # close sidebar-nav
    
    # Footer
    today = date.today().isoformat()
    footer_html = textwrap.dedent(f"""
        <div class="sidebar-footer">
            <div><span class="live-dot"></span>Live prices</div>
            <div>{today}</div>
        </div>
    """).strip()
    
    sidebar_html = textwrap.dedent(f"""
        <div class="custom-sidebar">
            {brand_html}
            {nav_html}
            {footer_html}
        </div>
    """).strip()
    return sidebar_html
