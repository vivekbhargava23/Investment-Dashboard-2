"""Tests for the explain-this-number component (TICKET-RD4).

Cover the pure prompt builder, the spec validation, and the render call-shape
(value + meaning tile, plus the how? popover). The component must format only —
it computes no finance math.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.ui.components.explainable_metric import (
    ExplanationSpec,
    build_explain_prompt,
    render_explainable_metric,
)


def _spec(**overrides: object) -> ExplanationSpec:
    base: dict[str, object] = {
        "label": "Herfindahl",
        "value_str": "3200",
        "meaning": "Concentration score on a 0–10000 scale.",
        "formula": ["HHI = Σ (weightᵢ %)²", "over every open position i."],
        "inputs": {"AAPL": "40.0%", "MSFT": "30.0%"},
        "source_note": "Weights use current market value.",
    }
    base.update(overrides)
    return ExplanationSpec(**base)  # type: ignore[arg-type]


def test_spec_requires_all_core_fields() -> None:
    with pytest.raises(ValidationError):
        ExplanationSpec(label="X", value_str="1")  # type: ignore[call-arg]


def test_spec_rejects_empty_formula() -> None:
    with pytest.raises(ValidationError):
        _spec(formula=[])


def test_spec_is_frozen() -> None:
    spec = _spec()
    with pytest.raises(ValidationError):
        spec.value_str = "9999"  # type: ignore[misc]


def test_build_prompt_is_complete_and_stable() -> None:
    spec = _spec()
    prompt = build_explain_prompt(spec)
    expected = (
        "Explain this portfolio metric to me: Herfindahl.\n"
        "\n"
        "Value: 3200\n"
        "What it means: Concentration score on a 0–10000 scale.\n"
        "\n"
        "Formula:\n"
        "  HHI = Σ (weightᵢ %)²\n"
        "  over every open position i.\n"
        "\n"
        "Inputs (the actual values behind this number):\n"
        "  AAPL: 40.0%\n"
        "  MSFT: 30.0%\n"
        "\n"
        "Note: Weights use current market value.\n"
        "\n"
        "Explain in plain language whether this value is healthy and what "
        "would move it."
    )
    assert prompt == expected


def test_build_prompt_handles_no_inputs() -> None:
    prompt = build_explain_prompt(_spec(inputs={}))
    assert "(no inputs provided)" in prompt


def test_render_emits_value_meaning_and_popover() -> None:
    spec = _spec(value_class="gain-amber")
    with (
        patch("app.ui.components.explainable_metric.st") as mock_st,
        patch("app.ui.components.explainable_metric.render_html") as mock_html,
    ):
        mock_st.button.return_value = False
        mock_st.session_state = {}
        render_explainable_metric(spec)

    # First render_html call is the value/meaning tile.
    card_html = mock_html.call_args_list[0].args[0]
    assert "Herfindahl" in card_html
    assert "3200" in card_html
    assert "metric-value gain-amber" in card_html
    assert "Concentration score" in card_html
    mock_st.popover.assert_called_once_with("how?")


def test_render_button_stashes_prompt_in_session_state() -> None:
    spec = _spec()
    session: dict[str, str] = {}
    with (
        patch("app.ui.components.explainable_metric.st") as mock_st,
        patch("app.ui.components.explainable_metric.render_html"),
    ):
        mock_st.button.return_value = True
        mock_st.session_state = session
        render_explainable_metric(spec)

    assert session["explain_prompt__Herfindahl"] == build_explain_prompt(spec)
    mock_st.code.assert_called_once()


def test_popover_is_context_manager_safe() -> None:
    """render must work with a real context-manager popover mock."""
    spec = _spec()
    popover_cm = MagicMock()
    popover_cm.__enter__ = MagicMock(return_value=popover_cm)
    popover_cm.__exit__ = MagicMock(return_value=False)
    with (
        patch("app.ui.components.explainable_metric.st") as mock_st,
        patch("app.ui.components.explainable_metric.render_html"),
    ):
        mock_st.popover.return_value = popover_cm
        mock_st.button.return_value = False
        mock_st.session_state = {}
        render_explainable_metric(spec)

    popover_cm.__enter__.assert_called_once()
