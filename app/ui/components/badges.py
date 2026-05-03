from typing import Literal


def render_thesis_badge(status: Literal["intact", "watch", "broken"]) -> str:
    """
    Returns an HTML string for a thesis badge.
    """
    if status == "intact":
        return '<span class="badge badge-green">Intact</span>'
    elif status == "watch":
        return '<span class="badge badge-amber">Watch</span>'
    elif status == "broken":
        return '<span class="badge badge-red">Broken</span>'
    else:
        raise ValueError(f"Invalid thesis status: {status}")

def render_severity_badge(severity: Literal["low", "med", "high"]) -> str:
    """
    Returns an HTML string for a severity badge.
    """
    if severity == "low":
        return '<span class="badge badge-green">Low</span>'
    elif severity == "med":
        return '<span class="badge badge-amber">Med</span>'
    elif severity == "high":
        return '<span class="badge badge-red">High</span>'
    else:
        raise ValueError(f"Invalid severity: {severity}")
