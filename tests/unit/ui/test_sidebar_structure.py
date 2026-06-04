"""Regression tests for sidebar HTML structure (TICKET-U1)."""
from datetime import date
from unittest.mock import patch

from app.ui.components.sidebar import _SECTIONS, NAV_ITEMS, _nav_item_html, render_sidebar

# ── Helpers ────────────────────────────────────────────────────────────────────

def _capture_sidebar_html(current_page: str = "overview", today: date = date(2026, 5, 9)) -> str:
    """Render sidebar and capture the HTML passed to render_html."""
    session = {"current_page": current_page}

    def fake_session_get(key: str, default: object = None) -> object:
        return session.get(key, default)

    with (
        patch("app.ui.components.sidebar.st") as mock_st,
        patch("app.ui.components.sidebar.render_html") as mock_render,
    ):
        mock_st.session_state.get = fake_session_get
        render_sidebar(today=today)
        assert mock_render.called, "render_html was not called"
        return mock_render.call_args[0][0]  # first positional arg


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_no_ghost_rows_nav_item_count() -> None:
    """nav-item-link count equals NAV_ITEMS count — no extra empty elements."""
    html = _capture_sidebar_html()
    count = html.count('class="nav-item-link"') + html.count('class="nav-item-link active"')
    assert count == len(NAV_ITEMS), (
        f"Expected {len(NAV_ITEMS)} nav items, found {count}"
    )


def test_three_section_labels_in_order() -> None:
    """Sidebar HTML contains exactly three section labels in PORTFOLIO/TOOLS/SETTINGS order."""
    html = _capture_sidebar_html()
    port_idx = html.index("PORTFOLIO")
    tools_idx = html.index("TOOLS")
    sett_idx = html.index("SETTINGS")
    assert port_idx < tools_idx < sett_idx

    plain = html.count('class="nav-section-label"')
    after = html.count('class="nav-section-label nav-section-label--after"')
    assert plain + after == 3, f"Expected 3 section label divs, found {plain + after}"


def test_portfolio_section_items() -> None:
    """PORTFOLIO section contains the dashboard portfolio pages in order."""
    html = _capture_sidebar_html()
    port_start = html.index("PORTFOLIO")
    tools_start = html.index("TOOLS")
    portfolio_block = html[port_start:tools_start]

    expected_ids = ["overview", "tax", "analytics", "company"]
    for page_id in expected_ids:
        assert f'href="/?page={page_id}"' in portfolio_block, (
            f"Expected {page_id} in PORTFOLIO section"
        )
    assert 'href="/?page=performance"' not in portfolio_block


def test_tools_section_items() -> None:
    """TOOLS section contains exactly: simulator."""
    html = _capture_sidebar_html()
    tools_start = html.index("TOOLS")
    sett_start = html.index("SETTINGS")
    tools_block = html[tools_start:sett_start]

    assert 'href="/?page=simulator"' in tools_block
    assert 'href="/?page=lots"' not in tools_block
    assert 'href="/?page=decision"' not in tools_block
    assert 'href="/?page=behaviour"' not in tools_block
    assert 'href="/?page=import_workbench"' not in tools_block


def test_settings_section_items() -> None:
    """SETTINGS section contains: manage, import_workbench, mappings."""
    html = _capture_sidebar_html()
    sett_start = html.index("SETTINGS")
    settings_block = html[sett_start:]
    assert 'href="/?page=manage"' in settings_block
    assert 'href="/?page=import_workbench"' in settings_block
    assert 'href="/?page=mappings"' in settings_block


def test_active_state_applied_to_correct_item() -> None:
    """With current_page='analytics', exactly one item has class 'active'."""
    html = _capture_sidebar_html(current_page="analytics")
    active_count = html.count('class="nav-item-link active"')
    assert active_count == 1, f"Expected 1 active item, found {active_count}"
    # The active item must be analytics
    active_anchor_idx = html.index('class="nav-item-link active"')
    href_before = html.rfind('<a href="', 0, active_anchor_idx)
    snippet = html[href_before : active_anchor_idx + 50]
    assert 'href="/?page=analytics"' in snippet


def test_no_underline_attribute_in_html() -> None:
    """Rendered sidebar HTML contains no inline text-decoration:underline."""
    html = _capture_sidebar_html()
    assert "text-decoration: underline" not in html
    assert "<u>" not in html


def test_brand_block_no_broker_reference() -> None:
    """Brand block contains 'Investment Panel' and no broker/country reference."""
    html = _capture_sidebar_html()
    assert "Investment Panel" in html
    assert "Scalable" not in html
    assert "Capital" not in html
    assert "· DE" not in html


def test_footer_present_with_date() -> None:
    """Footer contains 'Live prices', a live-dot element, and the injected date."""
    html = _capture_sidebar_html(today=date(2026, 5, 9))
    assert "Live prices" in html
    assert "live-dot" in html
    assert "2026-05-09" in html


def test_footer_date_is_deterministic() -> None:
    """Footer date changes with the injected 'today' argument."""
    html1 = _capture_sidebar_html(today=date(2024, 1, 1))
    html2 = _capture_sidebar_html(today=date(2026, 5, 9))
    assert "2024-01-01" in html1
    assert "2026-05-09" in html2
    assert html1.replace("2024-01-01", "DATE") == html2.replace("2026-05-09", "DATE")


def test_no_badge_renders_no_nav_badge_span() -> None:
    """_nav_item_html with badge=None produces no nav-badge span."""
    item = NAV_ITEMS[0]  # overview — badge=None
    result = _nav_item_html(item, active=False)
    assert "nav-badge" not in result


def test_nav_items_total_count() -> None:
    """NAV_ITEMS has exactly 8 entries after retiring Research (TICKET-RD0)."""
    assert len(NAV_ITEMS) == 8


def test_sections_cover_all_items() -> None:
    """_SECTIONS covers all NAV_ITEMS with no gaps or overlaps."""
    covered: set[int] = set()
    for _, start, end in _SECTIONS:
        for i in range(start, end):
            assert i not in covered, f"Index {i} covered twice"
            covered.add(i)
    assert covered == set(range(len(NAV_ITEMS)))
