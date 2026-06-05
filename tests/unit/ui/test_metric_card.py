"""Tests for the unified KPI tile component (TICKET-RD1).

One template (`build_metric_card`) now backs both the Overview and Tax KPI
tiles. These assert the shape, the class-driven styling (no inline `style=`),
and that data-derived strings are escaped.
"""
from __future__ import annotations

from app.ui.components.metric_card import build_metric_card


def test_minimal_card_has_label_and_value_no_sub() -> None:
    html = build_metric_card("Positions", "12")
    assert '<div class="metric-card">' in html
    assert '<div class="metric-label">Positions</div>' in html
    assert '<div class="metric-value">12</div>' in html
    assert "metric-sub" not in html


def test_no_inline_style_attributes() -> None:
    html = build_metric_card(
        "Total Unrealised Gain",
        "+€1.234",
        value_class="gain-positive",
        sub_value="+12.3%",
        sub_color="green",
        size="sm",
    )
    assert "style=" not in html


def test_value_class_and_size_applied_to_value() -> None:
    html = build_metric_card("Tax Headroom", "€800", value_class="gain-positive", size="sm")
    assert '<div class="metric-value sm gain-positive">€800</div>' in html


def test_lg_size_applied() -> None:
    html = build_metric_card("Big", "€1", size="lg")
    assert '<div class="metric-value lg">€1</div>' in html


def test_sub_value_with_color_modifier() -> None:
    html = build_metric_card(
        "Gain", "-€5", value_class="gain-negative", sub_value="-2%", sub_color="red"
    )
    assert '<div class="metric-sub red">-2%</div>' in html


def test_sub_color_default_has_no_modifier() -> None:
    html = build_metric_card("Cost", "€100", sub_value="cost basis")
    assert '<div class="metric-sub">cost basis</div>' in html


def test_card_class_appended() -> None:
    html = build_metric_card("Tax-free headroom", "€500", card_class="headroom-card")
    assert '<div class="metric-card headroom-card">' in html


def test_tooltip_is_escaped_title_attr() -> None:
    html = build_metric_card("Mean", "0.42", tooltip='A & B "ρ"')
    assert 'title="A &amp; B &quot;ρ&quot;"' in html


def test_label_and_value_are_escaped() -> None:
    html = build_metric_card("<b>L</b>", "<i>V</i>", sub_value="<u>S</u>")
    assert "<b>L</b>" not in html
    assert "&lt;b&gt;L&lt;/b&gt;" in html
    assert "&lt;i&gt;V&lt;/i&gt;" in html
    assert "&lt;u&gt;S&lt;/u&gt;" in html
