"""Tests for app/domain/tax/classification.py."""

import pytest

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.tax.classification import (
    InstrumentClassificationError,
    InstrumentKind,
    classify_instrument,
)


def _map_with(*pairs: tuple[str, str, InstrumentKind | None]) -> IsinMapDocument:
    """Build an IsinMapDocument from (isin, ticker, kind) triples."""
    entries = {
        isin: IsinMapping(ticker=ticker, name=ticker, status="mapped", instrument_kind=kind)
        for isin, ticker, kind in pairs
    }
    return IsinMapDocument(entries=entries)


_SEED_PORTFOLIO: list[tuple[str, InstrumentKind]] = [
    ("VUSA.DE", InstrumentKind.AKTIENFONDS),
    ("NVDA", InstrumentKind.AKTIE),
    ("RHM.DE", InstrumentKind.AKTIE),
    ("MU", InstrumentKind.AKTIE),
    ("ANET", InstrumentKind.AKTIE),
    ("MRVL", InstrumentKind.AKTIE),
    ("APD", InstrumentKind.AKTIE),
    ("AVGO", InstrumentKind.AKTIE),
    ("ETN", InstrumentKind.AKTIE),
    ("ASX", InstrumentKind.AKTIE),
    ("5631.T", InstrumentKind.AKTIE),
    ("HY9H.F", InstrumentKind.AKTIE),
]


def _seed_map() -> IsinMapDocument:
    return _map_with(*[(f"ISIN-{t}", t, k) for t, k in _SEED_PORTFOLIO])


@pytest.mark.parametrize("ticker,expected_kind", _SEED_PORTFOLIO)
def test_seed_portfolio_tickers_classify(ticker: str, expected_kind: InstrumentKind) -> None:
    assert classify_instrument(ticker, _seed_map()) == expected_kind


def test_unknown_ticker_raises_with_helpful_message() -> None:
    with pytest.raises(InstrumentClassificationError) as exc_info:
        classify_instrument("FOO.BAR", IsinMapDocument())
    msg = str(exc_info.value)
    assert "FOO.BAR" in msg
    assert "Mappings page" in msg


def test_ticker_in_map_but_no_kind_raises() -> None:
    isin_map = _map_with(("US1234567890", "DELL", None))
    with pytest.raises(InstrumentClassificationError) as exc_info:
        classify_instrument("DELL", isin_map)
    msg = str(exc_info.value)
    assert "DELL" in msg
    assert "Tax kind" in msg


def test_lowercase_input_is_normalized() -> None:
    isin_map = _seed_map()
    assert classify_instrument("nvda", isin_map) == InstrumentKind.AKTIE


def test_mixed_case_input_is_normalized() -> None:
    isin_map = _seed_map()
    assert classify_instrument("Vusa.De", isin_map) == InstrumentKind.AKTIENFONDS


def test_unknown_de_suffix_raises_not_silently_defaults() -> None:
    with pytest.raises(InstrumentClassificationError):
        classify_instrument("UNKNOWN.DE", IsinMapDocument())


def test_empty_isin_map_raises_for_any_ticker() -> None:
    with pytest.raises(InstrumentClassificationError):
        classify_instrument("NVDA", IsinMapDocument())


def test_ticker_match_is_case_insensitive_in_map() -> None:
    isin_map = _map_with(("US1234567890", "nvda", InstrumentKind.AKTIE))
    assert classify_instrument("NVDA", isin_map) == InstrumentKind.AKTIE
