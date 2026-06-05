import html

from app.ui.render import render_html

# sub_color tokens → modifier class on .metric-sub (defined in dark.css).
_SUB_COLOR_CLASS: dict[str, str] = {
    "default": "",
    "green": "green",
    "red": "red",
    "grey": "grey",
    "amber": "amber",
}
# size tokens → modifier class on .metric-value (defined in dark.css).
_SIZE_CLASS: dict[str, str] = {"md": "", "sm": "sm", "lg": "lg"}


def build_metric_card(
    label: str,
    value: str,
    *,
    sub_value: str | None = None,
    value_class: str | None = None,
    sub_color: str = "default",
    size: str = "md",
    tooltip: str | None = None,
    card_class: str | None = None,
) -> str:
    """Build a single KPI tile as an HTML string.

    One template for every KPI tile shape on the Overview and Tax pages. All
    styling lives in dark.css — no inline ``style=`` attributes. Data-derived
    strings are escaped via ``html.escape`` because callers emit the result
    through ``render_html`` (``unsafe_allow_html=True``).

    - ``value_class``: extra class on the value (e.g. ``gain-positive``).
    - ``sub_color``: one of ``default``/``green``/``red``/``grey``/``amber``.
    - ``size``: ``md`` (default), ``sm``, or ``lg``.
    - ``card_class``: extra class on the card (e.g. ``headroom-card``).
    """
    title_attr = f' title="{html.escape(tooltip)}"' if tooltip else ""
    size_cls = _SIZE_CLASS.get(size, "")
    value_classes = " ".join(c for c in ("metric-value", size_cls, value_class) if c)
    card_classes = " ".join(c for c in ("metric-card", card_class) if c)

    sub_html = ""
    if sub_value is not None:
        sub_color_cls = _SUB_COLOR_CLASS.get(sub_color, "")
        sub_classes = " ".join(c for c in ("metric-sub", sub_color_cls) if c)
        sub_html = f'<div class="{sub_classes}">{html.escape(sub_value)}</div>'

    return (
        f'<div class="{card_classes}"{title_attr}>'
        f'<div class="metric-label">{html.escape(label)}</div>'
        f'<div class="{value_classes}">{html.escape(value)}</div>'
        f"{sub_html}"
        f"</div>"
    )


def render_metric_card(
    label: str,
    value: str,
    *,
    sub_value: str | None = None,
    value_class: str | None = None,
    sub_color: str = "default",
    size: str = "md",
    tooltip: str | None = None,
    card_class: str | None = None,
) -> None:
    """Render a single KPI tile. See ``build_metric_card`` for the parameters."""
    render_html(
        build_metric_card(
            label,
            value,
            sub_value=sub_value,
            value_class=value_class,
            sub_color=sub_color,
            size=size,
            tooltip=tooltip,
            card_class=card_class,
        )
    )
