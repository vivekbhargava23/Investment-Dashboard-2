from __future__ import annotations

import html
from decimal import Decimal


def render_weight_bar(
    weight_pct: Decimal,
    *,
    scale_max: Decimal = Decimal("40"),
    danger_threshold: Decimal = Decimal("35"),
    warning_threshold: Decimal = Decimal("25"),
    label: str | None = None,
) -> str:
    """Return an inline weight-bar HTML snippet for render_html callers."""
    safe_weight = max(Decimal("0"), weight_pct)
    fill_pct = Decimal("0")
    if scale_max > 0:
        fill_pct = min(Decimal("100"), safe_weight / scale_max * Decimal("100"))

    css_class = _weight_class(
        safe_weight,
        danger_threshold=danger_threshold,
        warning_threshold=warning_threshold,
    )
    bar_label = f"{safe_weight:.1f}%" if label is None else html.escape(label)
    outer_style = "display: flex; align-items: center; gap: 4px;"
    track_style = (
        "width: 30px; height: 4px; background: var(--surface2); "
        "border-radius: 2px; overflow: hidden;"
    )
    fill_style = f"width: {fill_pct}%; height: 100%; background: var(--blue);"
    return (
        f'<div class="weight-bar {css_class}" style="{outer_style}">'
        f"<span>{bar_label}</span>"
        f'<div style="{track_style}">'
        f'<div class="weight-bar-fill" style="{fill_style}"></div>'
        f"</div></div>"
    )


def _weight_class(
    weight_pct: Decimal,
    *,
    danger_threshold: Decimal,
    warning_threshold: Decimal,
) -> str:
    if weight_pct > danger_threshold:
        return "weight-danger"
    if weight_pct > warning_threshold:
        return "weight-warning"
    return "weight-success"
