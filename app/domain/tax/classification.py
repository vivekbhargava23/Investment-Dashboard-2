"""Instrument classification for German tax purposes."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.isin_map import IsinMapDocument, IsinMapping


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
    """Look up by ticker across all ISIN map entries. Raise if missing or unclassified.

    A holding with no feed trades under its ISIN as a placeholder ticker (ADR-014
    rule 2), so a ticker that is really an ISIN — with or without an exchange
    suffix — is looked up as one. Without that, an instrument the map knows and
    has classified (a certificate, a crypto ETP: real holdings that simply have
    no price feed) is invisible here purely because its entry has no ticker, and
    one such holding takes the whole tax year down.
    """
    upper = ticker.upper()
    entry = _entry_for(upper, isin_map)
    if entry is None:
        raise InstrumentClassificationError(
            f"Ticker '{ticker}' is not in the ISIN map. "
            f"Open All instruments on the Sync tab and pick a price feed."
        )
    if entry.instrument_kind is None:
        raise InstrumentClassificationError(
            f"Ticker '{ticker}' has no tax classification. "
            f"Open All instruments on the Sync tab and pick a Tax kind."
        )
    return entry.instrument_kind


def _entry_for(upper: str, isin_map: IsinMapDocument) -> IsinMapping | None:
    """The mapping ``upper`` denotes: its feed ticker first, then its ISIN."""
    for entry in isin_map.entries.values():
        if entry.ticker and entry.ticker.upper() == upper:
            return entry
    by_isin = {isin.upper(): entry for isin, entry in isin_map.entries.items()}
    return by_isin.get(upper) or by_isin.get(upper.split(".", 1)[0])
