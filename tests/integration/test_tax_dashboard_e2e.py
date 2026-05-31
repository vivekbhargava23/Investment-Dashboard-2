# ruff: noqa: E501
"""Integration tests for the Tax Dashboard data-loading functions."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.positions import LivePosition, OpenLot, Position
from app.domain.tax.classification import InstrumentClassificationError, InstrumentKind
from app.domain.tax.models import FilingStatus, TaxProfile
from app.services.tax_planning import (
    compute_current_tax_summary,
    compute_per_position_harvest_impact,
)

_EUR = Currency.EUR
_USD = Currency.USD
_SINGLE = TaxProfile(filing_status=FilingStatus.SINGLE)
_AS_OF = datetime(2026, 6, 1, 12, 0)


def _isin_map(*pairs: tuple[str, InstrumentKind]) -> IsinMapDocument:
    entries = {
        f"ISIN-{ticker}": IsinMapping(ticker=ticker, name=ticker, status="mapped", instrument_kind=kind)
        for ticker, kind in pairs
    }
    return IsinMapDocument(entries=entries)


_E2E_MAP = _isin_map(
    ("ETN", InstrumentKind.AKTIE),
    ("NVDA", InstrumentKind.AKTIE),
)


def _m(v: str, ccy: Currency = _EUR) -> Money:
    return Money(amount=Decimal(v), currency=ccy)


def _eur(v: str) -> Money:
    return _m(v, _EUR)


def _buy(ticker: str, d: str, shares: str, price: str, ccy: Currency = _EUR, fx: str = "1") -> Transaction:
    return Transaction(
        ticker=ticker,
        type=TransactionType.BUY,
        trade_date=date.fromisoformat(d),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price), currency=ccy),
        fx_rate_eur=Decimal(fx),
    )


def _sell(ticker: str, d: str, shares: str, price: str, ccy: Currency = _EUR, fx: str = "1") -> Transaction:
    return Transaction(
        ticker=ticker,
        type=TransactionType.SELL,
        trade_date=date.fromisoformat(d),
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price), currency=ccy),
        fx_rate_eur=Decimal(fx),
    )


def _live_pos(
    ticker: str,
    cost_eur: str,
    live_value_eur: str,
    shares: str = "10",
) -> LivePosition:
    lot = OpenLot(
        source_transaction_id=f"t-{ticker}",
        ticker=ticker,
        trade_date=date(2025, 1, 1),
        remaining_shares=Decimal(shares),
        cost_per_share_native=_eur(str(Decimal(cost_eur) / Decimal(shares))),
        fx_rate_eur=Decimal("1"),
    )
    pos = Position(
        ticker=ticker,
        open_shares=Decimal(shares),
        open_lots=(lot,),
        realised_gain_eur_ytd=_eur("0"),
        cost_basis_eur=_eur(cost_eur),
    )
    gain = Decimal(live_value_eur) - Decimal(cost_eur)
    gain_pct = gain / Decimal(cost_eur) * Decimal("100") if Decimal(cost_eur) != 0 else Decimal("0")
    return LivePosition(
        position=pos,
        live_price_native=_eur(str(Decimal(live_value_eur) / Decimal(shares))),
        live_value_eur=_eur(live_value_eur),
        unrealised_gain_eur=Money(amount=gain, currency=_EUR),
        unrealised_gain_pct=gain_pct,
        current_fx_rate=Decimal("1"),
        staleness_reason=None,
    )


@pytest.mark.integration
def test_four_tile_summary_fixture() -> None:
    """Three-transaction portfolio produces expected four-tile values.

    Fixture: 1 ETN buy + 1 ETN 2026 sell + 1 NVDA buy.
    ETN gain (AKTIE, USD): buy 5 @ $100 FX 0.90 = €450; sell 2 @ $110 FX 0.91 = €200.20.
    Cost basis 2 lots = €180. Gain = €20.20.
    NVDA: unrealised only.
    Allowance €1,000 → all gains sheltered.
    """
    txs = [
        _buy("ETN", "2025-01-01", "5", "100", _USD, "0.90"),
        _sell("ETN", "2026-03-01", "2", "110", _USD, "0.91"),
        _buy("NVDA", "2025-06-01", "10", "100", _USD, "0.90"),
    ]
    summary = compute_current_tax_summary(
        transactions=txs,
        profile=_SINGLE,
        carryforward_eur_aktien=_eur("0"),
        carryforward_eur_general=_eur("0"),
        additional_dividend_income_eur=_eur("0"),
        additional_interest_income_eur=_eur("0"),
        as_of=datetime(2026, 12, 31),
        isin_map=_E2E_MAP,
    )
    assert summary.year == 2026
    assert summary.total_tax_owed_eur.amount == Decimal("0")
    assert summary.sparerpauschbetrag_remaining_eur.amount > Decimal("0")
    # Only ETN 2026 sell produces a gain; NVDA is unrealised
    assert len(summary.realised_gain_impacts) == 1


@pytest.mark.integration
def test_unclassified_ticker_error_surfaces_clearly() -> None:
    """An unclassified ticker in the harvest call raises InstrumentClassificationError."""
    live_pos = _live_pos("UNKNOWN_TICKER_XYZ", cost_eur="1000", live_value_eur="1200")
    summary = compute_current_tax_summary(
        transactions=[],
        profile=_SINGLE,
        carryforward_eur_aktien=_eur("0"),
        carryforward_eur_general=_eur("0"),
        additional_dividend_income_eur=_eur("0"),
        additional_interest_income_eur=_eur("0"),
        as_of=_AS_OF,
        isin_map=IsinMapDocument(),
    )
    with pytest.raises(InstrumentClassificationError):
        compute_per_position_harvest_impact(
            transactions=[],
            live_positions={"UNKNOWN_TICKER_XYZ": live_pos},
            current_summary=summary,
            profile=_SINGLE,
            carryforward_eur_aktien=_eur("0"),
            carryforward_eur_general=_eur("0"),
            additional_dividend_income_eur=_eur("0"),
            additional_interest_income_eur=_eur("0"),
            as_of=_AS_OF,
            isin_map=IsinMapDocument(),
        )
