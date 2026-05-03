import textwrap
import streamlit as st


def render_metric_card(
    label: str,
    value: str,
    subtitle: str | None = None,
    value_class: str | None = None,
    progress_pct: float | None = None
) -> None:
    """
    Renders a single KPI tile matching the mockup.
    """
    subtitle_html = ""
    if subtitle:
        cls = value_class if value_class else ""
        subtitle_html = f'<div class="metric-delta {cls}">{subtitle}</div>'
    
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
    
    st.markdown(textwrap.dedent(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            {subtitle_html}
            {progress_html}
        </div>
    """).strip(), unsafe_allow_html=True)
