"""Tests for app/domain/tax/classification.py."""

import pytest

from app.domain.tax.classification import (
    TICKER_KIND,
    InstrumentClassificationError,
    InstrumentKind,
    classify_instrument,
)

_EXPECTED_KINDS = {
    "VUSA.DE": InstrumentKind.AKTIENFONDS,
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


@pytest.mark.parametrize("ticker,expected_kind", _EXPECTED_KINDS.items())
def test_seed_portfolio_tickers_classify(ticker: str, expected_kind: InstrumentKind) -> None:
    assert classify_instrument(ticker) == expected_kind


def test_unknown_ticker_raises_with_helpful_message() -> None:
    with pytest.raises(InstrumentClassificationError) as exc_info:
        classify_instrument("FOO.BAR")
    msg = str(exc_info.value)
    assert "FOO.BAR" in msg
    assert "app/domain/tax/classification.py" in msg


def test_lowercase_input_is_normalized() -> None:
    assert classify_instrument("nvda") == InstrumentKind.AKTIE


def test_mixed_case_input_is_normalized() -> None:
    assert classify_instrument("Vusa.De") == InstrumentKind.AKTIENFONDS


def test_unknown_de_suffix_raises_not_silently_defaults() -> None:
    # An unknown .DE ticker should raise, not fall back to AKTIE.
    with pytest.raises(InstrumentClassificationError):
        classify_instrument("UNKNOWN.DE")


def test_ticker_kind_covers_all_seed_tickers() -> None:
    for ticker in _EXPECTED_KINDS:
        assert ticker in TICKER_KIND
