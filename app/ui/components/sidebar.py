from datetime import date
from typing import Any

import streamlit as st

from app.ui.render import render_html

NAV_ITEMS: list[dict[str, Any]] = [
    # PORTFOLIO
    {"id": "overview",    "label": "Live Overview",      "icon": "◉",  "badge": None},
    {"id": "performance", "label": "Performance",        "icon": "↗",  "badge": None},
    {"id": "tax",         "label": "Tax Dashboard",      "icon": "§",  "badge": None},
    {"id": "analytics",   "label": "Analytics & Risk",   "icon": "⬡",  "badge": None},
    {"id": "research",    "label": "Research",           "icon": "📈", "badge": None},
    # TOOLS
    {"id": "simulator",   "label": "Sell Simulator",     "icon": "⚡", "badge": None},
    {"id": "lots",        "label": "Lot Ledger",         "icon": "≡",  "badge": None},
    {
        "id": "decision",
        "label": "Decision Gates",
        "icon": "▲",
        "badge": {"text": "3 flags", "color": ""},
    },
    {"id": "behaviour",   "label": "Behavioural Ledger", "icon": "◎",  "badge": None},
    # SETTINGS
    {"id": "manage",      "label": "Manage Portfolio",   "icon": "⚙",  "badge": None},
]

_SECTIONS: list[tuple[str, int, int]] = [
    ("PORTFOLIO", 0, 5),
    ("TOOLS",     5, 9),
    ("SETTINGS",  9, 10),
]


def _nav_item_html(item: dict[str, Any], *, active: bool) -> str:
    active_class = " active" if active else ""
    badge = ""
    if item["badge"]:
        badge = f'<span class="nav-badge {item["badge"]["color"]}">{item["badge"]["text"]}</span>'
    return (
        f'<a href="/?page={item["id"]}" target="_self" class="nav-item-link{active_class}">'
        f'<span class="nav-icon">{item["icon"]}</span>'
        f'<span>{item["label"]}</span>'
        f'{badge}'
        f'</a>'
    )


def render_sidebar(*, today: date | None = None) -> None:
    current_page = st.session_state.get("current_page", "overview")
    as_of = today or date.today()

    brand_html = (
        '<div class="sidebar-logo">'
        '<div class="mark">'
        '<div class="icon">📈</div>'
        '<div class="name">Investment Panel</div>'
        '</div>'
        '</div>'
    )

    nav_parts: list[str] = ['<div class="sidebar-nav">']
    for i, (label, start, end) in enumerate(_SECTIONS):
        extra = " nav-section-label--after" if i > 0 else ""
        nav_parts.append(f'<div class="nav-section-label{extra}">{label}</div>')
        for item in NAV_ITEMS[start:end]:
            nav_parts.append(_nav_item_html(item, active=current_page == item["id"]))
    nav_parts.append('</div>')
    nav_html = "".join(nav_parts)

    footer_html = (
        f'<div class="sidebar-footer">'
        f'<div><span class="live-dot"></span>Live prices</div>'
        f'<div>{as_of.isoformat()}</div>'
        f'</div>'
    )

    render_html(
        f'<div class="custom-sidebar">'
        f'{brand_html}'
        f'{nav_html}'
        f'{footer_html}'
        f'</div>'
    )
