"""A metric tile that can explain itself (TICKET-RD4).

``render_explainable_metric`` renders a KPI value plus a one-line meaning and a
``how?`` popover holding the formula and the actual inputs that produced the
number. It also offers an "Ask AI to explain this number" affordance that
assembles a copyable prompt via the pure ``build_explain_prompt`` — there is no
inference backend in this ticket.

The component computes no finance math. It only formats the strings the caller
passes; all domain math stays in ``app/domain/``.
"""

from __future__ import annotations

import html

import streamlit as st
from pydantic import BaseModel, ConfigDict, Field

from app.ui.render import render_html


class ExplanationSpec(BaseModel):
    """Everything the explain component needs to render and to build a prompt.

    All fields are pre-formatted display strings — the caller does the math.
    """

    model_config = ConfigDict(frozen=True)

    label: str
    value_str: str
    meaning: str
    formula: list[str] = Field(min_length=1)
    inputs: dict[str, str]
    source_note: str
    value_class: str | None = None


def build_explain_prompt(spec: ExplanationSpec) -> str:
    """Assemble a stable, self-contained prompt a user can paste into any AI.

    Pure: no Streamlit, no I/O. The output is deterministic for a given spec so
    it is safe to snapshot in tests.
    """
    lines = [
        f"Explain this portfolio metric to me: {spec.label}.",
        "",
        f"Value: {spec.value_str}",
        f"What it means: {spec.meaning}",
        "",
        "Formula:",
        *[f"  {line}" for line in spec.formula],
        "",
        "Inputs (the actual values behind this number):",
    ]
    if spec.inputs:
        lines.extend(f"  {name}: {value}" for name, value in spec.inputs.items())
    else:
        lines.append("  (no inputs provided)")
    lines.extend(
        [
            "",
            f"Note: {spec.source_note}",
            "",
            "Explain in plain language whether this value is healthy and what "
            "would move it.",
        ]
    )
    return "\n".join(lines)


def _build_inputs_table_html(inputs: dict[str, str]) -> str:
    if not inputs:
        return '<div class="metric-sub">No inputs to show.</div>'
    rows = "".join(
        "<tr>"
        f"<td><strong>{html.escape(name)}</strong></td>"
        f'<td class="font-mono text-right">{html.escape(value)}</td>'
        "</tr>"
        for name, value in inputs.items()
    )
    return (
        '<table class="positions-table" style="width: 100%; border-collapse: '
        'collapse; font-size: 13px;"><tbody>' + rows + "</tbody></table>"
    )


def render_explainable_metric(spec: ExplanationSpec) -> None:
    """Render the value + meaning tile, a ``how?`` popover, and the AI affordance.

    The assembled AI prompt is stashed under a per-label session-state key
    (``explain_prompt__<label>``) and shown in a copyable code block when the
    user asks for it, so no inference backend is required.
    """
    value_classes = " ".join(
        c for c in ("metric-value", spec.value_class) if c
    )
    render_html(
        '<div class="metric-card">'
        f'<div class="metric-label">{html.escape(spec.label)}</div>'
        f'<div class="{value_classes}">{html.escape(spec.value_str)}</div>'
        f'<div class="metric-sub">{html.escape(spec.meaning)}</div>'
        "</div>"
    )

    with st.popover("how?"):
        st.markdown(f"**{spec.label}**")
        st.markdown("\n".join(f"`{line}`" for line in spec.formula))
        render_html(_build_inputs_table_html(spec.inputs))
        st.caption(spec.source_note)

        prompt_key = f"explain_prompt__{spec.label}"
        if st.button("Ask AI to explain this number", key=f"explain_btn__{spec.label}"):
            st.session_state[prompt_key] = build_explain_prompt(spec)
        if st.session_state.get(prompt_key):
            st.code(st.session_state[prompt_key], language="text")
