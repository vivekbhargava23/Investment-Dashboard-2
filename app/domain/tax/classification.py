"""Instrument classification for German tax purposes."""

from __future__ import annotations

from enum import StrEnum


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


# Single source of truth for ticker → instrument kind.
# Adding a new ticker requires adding exactly one row here.
# Never use heuristics (e.g. "if it ends in .DE it's probably an ETF").
# Heuristics reproduce the silent-default anti-pattern from TICKET-008c.
TICKER_KIND: dict[str, InstrumentKind] = {
    # ETFs (Aktienfonds — UCITS-compliant equity funds)
    "VUSA.DE": InstrumentKind.AKTIENFONDS,
    # Individual shares (Aktien — direct equity)
    "NVDA": InstrumentKind.AKTIE,
    "RHM.DE": InstrumentKind.AKTIE,
    "MU": InstrumentKind.AKTIE,
    "ANET": InstrumentKind.AKTIE,
    "MRVL": InstrumentKind.AKTIE,
    "APD": InstrumentKind.AKTIE,
    "AVGO": InstrumentKind.AKTIE,
    "ETN": InstrumentKind.AKTIE,
    "ASX": InstrumentKind.AKTIE,
    "5631.T": InstrumentKind.AKTIE,
    "HY9H.F": InstrumentKind.AKTIE,
}


def classify_instrument(ticker: str) -> InstrumentKind:
    """
    Return the German tax InstrumentKind for a ticker.

    Raises InstrumentClassificationError if the ticker is not in TICKER_KIND.
    Tickers are upper-cased before lookup.
    """
    upper = ticker.upper()
    kind = TICKER_KIND.get(upper)
    if kind is None:
        raise InstrumentClassificationError(
            f"Ticker '{ticker}' has no instrument-kind classification. "
            f"Add it to TICKER_KIND in app/domain/tax/classification.py."
        )
    return kind
