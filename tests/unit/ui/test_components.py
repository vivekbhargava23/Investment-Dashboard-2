import pytest

import app.ui.pages.analytics as analytics
import app.ui.pages.behaviour as behaviour
import app.ui.pages.company as company
import app.ui.pages.decision as decision
import app.ui.pages.lots as lots
import app.ui.pages.manage as manage
import app.ui.pages.overview as overview
import app.ui.pages.performance as performance
import app.ui.pages.tax as tax
from app.ui.components.badges import render_severity_badge, render_thesis_badge
from app.ui.components.sidebar import NAV_ITEMS
from app.ui.components.topbar import PAGE_TITLES


def test_render_thesis_badge():
    assert "intact" in render_thesis_badge("intact").lower()
    assert "badge-green" in render_thesis_badge("intact")
    assert "amber" in render_thesis_badge("watch")
    assert "red" in render_thesis_badge("broken")
    with pytest.raises(ValueError):
        render_thesis_badge("invalid") # type: ignore

def test_render_severity_badge():
    assert "low" in render_severity_badge("low").lower()
    assert "badge-green" in render_severity_badge("low")
    assert "amber" in render_severity_badge("med")
    assert "red" in render_severity_badge("high")
    with pytest.raises(ValueError):
        render_severity_badge("invalid") # type: ignore

def test_nav_items_consistency():
    assert len(NAV_ITEMS) == 12
    for item in NAV_ITEMS:
        assert "id" in item
        assert "label" in item
        assert "icon" in item
        assert "badge" in item
        # Check that every nav item has a corresponding title
        assert item["id"] in PAGE_TITLES

def test_page_registry_presence():
    # Introspect that render functions exist
    assert callable(overview.render)
    assert callable(analytics.render)
    assert callable(performance.render)
    assert callable(tax.render)
    assert callable(company.render)
    assert callable(decision.render)
    assert callable(behaviour.render)
    assert callable(lots.render)
    assert callable(manage.render)
