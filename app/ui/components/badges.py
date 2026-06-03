from typing import Literal


def render_thesis_badge(status: Literal["intact", "watch", "broken", "unknown"]) -> str:
    """
    Returns an HTML string for a thesis badge.

    "unknown" is the honest rendering for a holding with no thesis entry in
    data/thesis.json — it must never be silently defaulted to "intact".
    """
    if status == "intact":
        return '<span class="badge badge-green">Intact</span>'
    elif status == "watch":
        return '<span class="badge badge-amber">Watch</span>'
    elif status == "broken":
        return '<span class="badge badge-red">Broken</span>'
    elif status == "unknown":
        return '<span class="badge badge-grey">Unknown</span>'
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
