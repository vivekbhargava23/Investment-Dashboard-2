"""Instrument classification for German tax purposes."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.isin_map import IsinMapDocument


class InstrumentKind(StrEnum):
    """German tax instrument classification."""

    AKTIE = "AKTIE"
    AKTIENFONDS = "AKTIENFONDS"
    MISCHFONDS = "MISCHFONDS"
    IMMOBILIENFONDS = "IMMOBILIENFONDS"
    IMMOBILIENFONDS_AUSLAND = "IMMOBILIENFONDS_AUSLAND"
    RENTENFONDS = "RENTENFONDS"
    SONSTIGE = "SONSTIGE"
    DIVIDENDE = "DIVIDENDE"
    ZINSEN = "ZINSEN"


class InstrumentClassificationError(Exception):
    """Raised when a ticker has no instrument-kind classification."""

    pass


def classify_instrument(ticker: str, isin_map: IsinMapDocument) -> InstrumentKind:
    """Look up by ticker across all ISIN map entries. Raise if missing or unclassified."""
    upper = ticker.upper()
    for entry in isin_map.entries.values():
        if entry.ticker and entry.ticker.upper() == upper:
            if entry.instrument_kind is None:
                raise InstrumentClassificationError(
                    f"Ticker '{ticker}' has no tax classification. "
                    f"Open the Mappings page and pick a Tax kind."
                )
            return entry.instrument_kind
    raise InstrumentClassificationError(
        f"Ticker '{ticker}' is not in the ISIN map. "
        f"Open the Mappings page and create the mapping."
    )
