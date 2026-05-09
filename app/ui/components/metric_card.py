import html
import textwrap

from app.ui.render import render_html


def render_metric_card(
    label: str,
    value: str,
    subtitle: str | None = None,
    value_class: str | None = None,
    progress_pct: float | None = None,
    tooltip: str | None = None,
) -> None:
    """
    Renders a single KPI tile matching the mockup.
    """
    title_attr = f' title="{html.escape(tooltip)}"' if tooltip else ""
    subtitle_html = ""
    if subtitle:
        cls = value_class if value_class else ""
        subtitle_html = f'<div class="metric-delta {cls}">{html.escape(subtitle)}</div>'
    
    progress_html = ""
    if progress_pct is not None:
        # Simple CSS progress bar
        progress_html = textwrap.dedent(f"""
            <div style="width: 100%; background: var(--surface2); height: 4px; 
                        border-radius: 2px; margin-top: 10px;">
                <div style="width: {progress_pct}%; background: var(--accent); 
                            height: 100%; border-radius: 2px;"></div>
            </div>
        """).strip()
    
    value_cls = f" {value_class}" if value_class else ""
    render_html(textwrap.dedent(f"""
        <div class="metric-card"{title_attr}>
            <div class="metric-label">{html.escape(label)}</div>
            <div class="metric-value{value_cls}">{html.escape(value)}</div>
            {subtitle_html}
            {progress_html}
        </div>
    """))
