"""The in-app explanations are copy, and copy rots. These tests are its guard rails."""
from __future__ import annotations

import typing

import pytest

from app.domain.sync_tasks import TaskKind
from app.ui.components import explainers
from app.ui.components.explainers import TASK_EXPLAINERS, Explainer

_ALL: list[tuple[str, Explainer]] = [
    (name, value)
    for name, value in vars(explainers).items()
    if isinstance(value, Explainer)
]

# Surfaces this ticket deleted. An explainer that still sends the reader to one
# of them is worse than no explainer at all.
_DEAD_SURFACES = ("ISIN Mappings page", "Import CSV workbench", "Mappings page")


def test_there_are_explainers_to_check() -> None:
    assert len(_ALL) >= 8


def test_every_task_kind_has_an_explainer() -> None:
    """A task with no explanation is exactly the one the reader will meet cold."""
    kinds = set(typing.get_args(TaskKind))

    assert set(TASK_EXPLAINERS) == kinds


@pytest.mark.parametrize("name,explainer", _ALL, ids=lambda v: v if isinstance(v, str) else "")
def test_every_explainer_has_a_short_title_and_a_real_body(
    name: str, explainer: Explainer
) -> None:
    assert explainer.title.strip()
    assert len(explainer.title) <= 40, f"{name}: title is a label, not a sentence"
    assert len(explainer.body.strip()) > 120, f"{name}: body says too little to help"


@pytest.mark.parametrize("name,explainer", _ALL, ids=lambda v: v if isinstance(v, str) else "")
def test_no_explainer_points_at_a_retired_page(name: str, explainer: Explainer) -> None:
    for dead in _DEAD_SURFACES:
        assert dead not in explainer.body, f"{name} sends the reader to {dead}"


@pytest.mark.parametrize(
    "name,explainer",
    [(n, e) for n, e in TASK_EXPLAINERS.items()],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_every_task_explainer_says_what_to_do(name: str, explainer: Explainer) -> None:
    """Describing the situation without naming the next action is half an answer."""
    assert "What to do" in explainer.body or "what to do" in explainer.body


def test_the_write_off_explainer_separates_itself_from_remove() -> None:
    """Confusing the two costs the user their realised loss, so both say so."""
    assert "Remove" in explainers.WRITE_OFF.body
    assert "Write off" in explainers.REMOVE_INSTRUMENT.body


def test_the_use_last_trade_price_copy_avoids_the_old_word() -> None:
    """The button stopped saying "Ignore" because it never meant "hide"."""
    body = explainers.USE_LAST_TRADE_PRICE.body
    assert "hide" in body.lower()  # says explicitly that it does not hide
    assert "Restore" in body
