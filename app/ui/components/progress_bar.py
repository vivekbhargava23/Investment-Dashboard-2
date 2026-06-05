from __future__ import annotations


def render_progress_bar(pct: float, *, height_px: int = 8) -> str:
    """Return a horizontal progress-bar snippet for ``render_html`` callers.

    The track and fill colours live in dark.css (``.progress-track`` /
    ``.progress-fill``). The fill width and track height are intrinsically
    dynamic, so they are the only inline ``style`` values — kept here inside a
    reusable component so the page modules stay free of inline styles.
    """
    clamped = max(0.0, min(100.0, pct))
    return (
        f'<div class="progress-track" style="height: {height_px}px;">'
        f'<div class="progress-fill" style="width: {clamped:.1f}%;"></div>'
        f"</div>"
    )
