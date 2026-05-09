from __future__ import annotations

from decimal import Decimal

from app.ui.components.weight_bar import render_weight_bar


def test_weight_bar_representative_html_snapshot() -> None:
    html = render_weight_bar(Decimal("18.5"))

    assert 'class="weight-bar weight-success"' in html
    assert "display: flex; align-items: center; gap: 4px;" in html
    assert "<span>18.5%</span>" in html
    assert "background: var(--surface2)" in html
    assert "width: 46.2500%" in html


def test_weight_bar_danger_warning_success_classes() -> None:
    assert "weight-danger" in render_weight_bar(Decimal("36"))
    assert "weight-warning" in render_weight_bar(Decimal("30"))
    assert "weight-success" in render_weight_bar(Decimal("15"))


def test_weight_bar_zero_is_valid() -> None:
    html = render_weight_bar(Decimal("0"))
    assert "<span>0.0%</span>" in html
    assert "width: 0%" in html


def test_weight_bar_clips_above_scale_max() -> None:
    html = render_weight_bar(Decimal("45"), scale_max=Decimal("40"))
    assert "width: 100%" in html


def test_weight_bar_escapes_custom_label() -> None:
    html = render_weight_bar(Decimal("10"), label='<script>alert("x")</script>')
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
