"""
Pure-data unit tests for the EUR-native transaction-building pipeline.
These tests exercise app.services.trading.build_transaction directly.
No Streamlit context required.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.domain.fifo import SellExceedsOpenSharesError, compute_positions
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ports.price_feed import PriceUnavailableError
from app.services.trading import build_transaction
from tests.fakes.fx_feed import FakeFxProvider
from tests.fakes.price_feed import FakePriceProvider

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_TRADE_DATE = date(2026, 5, 4)

_FAKE_PRICES = FakePriceProvider(
    historical_prices={
        ("APD", _TRADE_DATE): Money(amount=Decimal("298.35"), currency=Currency.USD),
        ("5631.T", _TRADE_DATE): Money(amount=Decimal("4500"), currency=Currency.JPY),
    }
)

_FAKE_FX = FakeFxProvider(
    historical_rates={
        (Currency.USD, Currency.EUR, _TRADE_DATE): Decimal("0.8552"),
        (Currency.JPY, Currency.EUR, _TRADE_DATE): Decimal("0.006111"),
    }
)


# ---------------------------------------------------------------------------
# EUR-native happy path
# ---------------------------------------------------------------------------

def test_eur_native_happy_path() -> None:
    tx, dev = build_transaction(
        ticker="RHM.DE",
        tx_type=TransactionType.BUY,
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=Decimal("1388.20"),
        fees_eur=Decimal("0.99"),
        currency=Currency.EUR,
        price_provider=_FAKE_PRICES,
        fx_provider=_FAKE_FX,
    )
    assert tx.ticker == "RHM.DE"
    # net_eur = 1388.20 - 0.99 = 1387.21
    assert tx.price_native == Money(amount=Decimal("1387.2100"), currency=Currency.EUR)
    assert tx.fx_rate_eur == Decimal("1")
    assert tx.fees_native is not None
    assert tx.fees_native.currency == Currency.EUR
    assert dev is None


def test_eur_native_cost_eur_round_trips() -> None:
    eur_total = Decimal("1388.20")
    tx, _ = build_transaction(
        ticker="RHM.DE",
        tx_type=TransactionType.BUY,
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=eur_total,
        fees_eur=Decimal("0.99"),
        currency=Currency.EUR,
        price_provider=_FAKE_PRICES,
        fx_provider=_FAKE_FX,
    )
    assert tx.cost_eur.amount == eur_total


def test_eur_native_zero_fees() -> None:
    tx, dev = build_transaction(
        ticker="RHM.DE",
        tx_type=TransactionType.BUY,
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=Decimal("1452.75"),
        fees_eur=Decimal("0"),
        currency=Currency.EUR,
        price_provider=_FAKE_PRICES,
        fx_provider=_FAKE_FX,
    )
    assert tx.fees_native is None
    assert dev is None


# ---------------------------------------------------------------------------
# USD happy path
# ---------------------------------------------------------------------------

def test_usd_happy_path() -> None:
    # APD historical close = $298.35
    # eur_total = 256.42, fees = 0.99, net = 255.43
    # implied_fx = 255.43 / (1 × 298.35) = ~0.856112
    tx, dev = build_transaction(
        ticker="APD",
        tx_type=TransactionType.BUY,
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=Decimal("256.42"),
        fees_eur=Decimal("0.99"),
        currency=Currency.USD,
        price_provider=_FAKE_PRICES,
        fx_provider=_FAKE_FX,
    )
    assert tx.ticker == "APD"
    assert tx.price_native == Money(amount=Decimal("298.3500"), currency=Currency.USD)
    assert tx.price_native.currency == Currency.USD
    assert tx.fx_rate_eur > Decimal("0.85")
    assert tx.fx_rate_eur < Decimal("0.87")
    # Deviation from ECB 0.8552 should be < 2%
    assert dev is not None
    assert dev < Decimal("2")


def test_usd_cost_eur_round_trips() -> None:
    eur_total = Decimal("256.42")
    fees_eur = Decimal("0.99")
    tx, _ = build_transaction(
        ticker="APD",
        tx_type=TransactionType.BUY,
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=eur_total,
        fees_eur=fees_eur,
        currency=Currency.USD,
        price_provider=_FAKE_PRICES,
        fx_provider=_FAKE_FX,
    )
    # Round-trip: tx.cost_eur should equal eur_total within 1 cent rounding
    assert abs(tx.cost_eur.amount - eur_total) < Decimal("0.02")


# ---------------------------------------------------------------------------
# JPY happy path
# ---------------------------------------------------------------------------

def test_jpy_happy_path() -> None:
    # 5631.T historical close = ¥4500
    # eur_total = 27.50, fees = 0.99, net = 26.51
    # implied_fx = 26.51 / (1 × 4500) = ~0.005891
    tx, dev = build_transaction(
        ticker="5631.T",
        tx_type=TransactionType.BUY,
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=Decimal("27.50"),
        fees_eur=Decimal("0.99"),
        currency=Currency.JPY,
        price_provider=_FAKE_PRICES,
        fx_provider=_FAKE_FX,
    )
    assert tx.ticker == "5631.T"
    assert tx.price_native.currency == Currency.JPY
    assert tx.price_native.amount == Decimal("4500.0000")
    assert dev is not None  # JPY ECB rate is in the fake provider


# ---------------------------------------------------------------------------
# Deviation warning
# ---------------------------------------------------------------------------

def test_deviation_warning_fires_for_large_deviation() -> None:
    # Historical close = $298.35, ECB = 0.8552
    # User enters eur_total = 300.00 (typo — should be ~256)
    # implied_fx = (300 - 0.99) / 298.35 ≈ 1.00 >> 0.8552 → >2% deviation
    tx, dev = build_transaction(
        ticker="APD",
        tx_type=TransactionType.BUY,
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=Decimal("300.00"),
        fees_eur=Decimal("0.99"),
        currency=Currency.USD,
        price_provider=_FAKE_PRICES,
        fx_provider=_FAKE_FX,
    )
    assert dev is not None
    assert dev > Decimal("2"), f"Expected >2% deviation, got {dev}"


def test_deviation_none_when_fx_provider_fails() -> None:
    empty_fx = FakeFxProvider()  # no rates configured
    tx, dev = build_transaction(
        ticker="APD",
        tx_type=TransactionType.BUY,
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=Decimal("256.42"),
        fees_eur=Decimal("0.99"),
        currency=Currency.USD,
        price_provider=_FAKE_PRICES,
        fx_provider=empty_fx,
    )
    assert dev is None  # graceful degradation


# ---------------------------------------------------------------------------
# FIFO sell guard
# ---------------------------------------------------------------------------

def _make_buy(ticker: str, shares: Decimal, currency: Currency, price: Decimal) -> Transaction:
    fx = Decimal("1") if currency == Currency.EUR else Decimal("0.90")
    return Transaction(
        type=TransactionType.BUY,
        ticker=ticker,
        trade_date=_TRADE_DATE,
        shares=shares,
        price_native=Money(amount=price, currency=currency),
        fx_rate_eur=fx,
    )


def test_fifo_sell_guard_raises_on_excess() -> None:
    existing = [_make_buy("NVDA", Decimal("5"), Currency.USD, Decimal("100"))]
    tx_sell, _ = build_transaction(
        ticker="NVDA",
        tx_type=TransactionType.SELL,
        trade_date=date(2026, 5, 5),
        shares=Decimal("10"),
        eur_total=Decimal("900"),
        fees_eur=Decimal("0.99"),
        currency=Currency.USD,
        price_provider=FakePriceProvider(
            historical_prices={
                ("NVDA", date(2026, 5, 5)): Money(amount=Decimal("100"), currency=Currency.USD)
            }
        ),
        fx_provider=FakeFxProvider(),
    )
    with pytest.raises(SellExceedsOpenSharesError):
        compute_positions(existing + [tx_sell])


def test_fifo_sell_guard_passes_on_valid_sell() -> None:
    existing = [_make_buy("NVDA", Decimal("10"), Currency.USD, Decimal("100"))]
    tx_sell, _ = build_transaction(
        ticker="NVDA",
        tx_type=TransactionType.SELL,
        trade_date=date(2026, 5, 5),
        shares=Decimal("5"),
        eur_total=Decimal("500"),
        fees_eur=Decimal("0.99"),
        currency=Currency.USD,
        price_provider=FakePriceProvider(
            historical_prices={
                ("NVDA", date(2026, 5, 5)): Money(amount=Decimal("100"), currency=Currency.USD)
            }
        ),
        fx_provider=FakeFxProvider(),
    )
    positions = compute_positions(existing + [tx_sell])
    assert positions["NVDA"].open_shares == Decimal("5")


# ---------------------------------------------------------------------------
# Validator catches mismatch (TICKET-008c regression)
# ---------------------------------------------------------------------------

def test_validator_rejects_ticker_currency_mismatch() -> None:
    """Transaction validator must reject 5631.T priced in USD regardless of submit path."""
    with pytest.raises(ValidationError, match="5631.T trades in JPY"):
        Transaction(
            type=TransactionType.BUY,
            ticker="5631.T",
            trade_date=_TRADE_DATE,
            shares=Decimal("1"),
            price_native=Money(amount=Decimal("4200"), currency=Currency.USD),
            fx_rate_eur=Decimal("0.93"),
        )


# ---------------------------------------------------------------------------
# _render_recording_preview — EUR price check
# ---------------------------------------------------------------------------

@patch("app.ui.pages.manage.get_price_provider")
@patch("app.ui.pages.manage.st")
def test_eur_price_check_within_tolerance(mock_st: MagicMock, mock_get_price: MagicMock) -> None:
    # RHM.DE market close = €125.00; user total implies €125.50 per share (< 2% off)
    mock_get_price.return_value.get_historical_close.return_value = Money(
        amount=Decimal("125.00"), currency=Currency.EUR
    )
    from app.ui.pages.manage import _render_recording_preview

    price_available, deviation_pct = _render_recording_preview(
        ticker="RHM.DE",
        currency=Currency.EUR,
        tx_type="Buy",
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=Decimal("126.49"),   # net = 125.50 after 0.99 fees → 0.4% off
        fees_eur=Decimal("0.99"),
    )

    assert price_available is True
    assert deviation_pct is not None
    assert deviation_pct < Decimal("2")
    mock_st.warning.assert_not_called()


@patch("app.ui.pages.manage.get_price_provider")
@patch("app.ui.pages.manage.st")
def test_eur_deviation_triggers_warning(mock_st: MagicMock, mock_get_price: MagicMock) -> None:
    # RHM.DE market close = €125.00; user total €150 implies €150/share — 20% off
    mock_get_price.return_value.get_historical_close.return_value = Money(
        amount=Decimal("125.00"), currency=Currency.EUR
    )
    from app.ui.pages.manage import _render_recording_preview

    price_available, deviation_pct = _render_recording_preview(
        ticker="RHM.DE",
        currency=Currency.EUR,
        tx_type="Buy",
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=Decimal("150.00"),
        fees_eur=Decimal("0"),
    )

    assert price_available is True
    assert deviation_pct is not None
    assert deviation_pct > Decimal("2")
    mock_st.warning.assert_called_once()


@patch("app.ui.pages.manage.get_price_provider")
@patch("app.ui.pages.manage.st")
def test_eur_unavailable_returns_true_none(mock_st: MagicMock, mock_get_price: MagicMock) -> None:
    # Price feed raises PriceUnavailableError — form is still usable
    mock_get_price.return_value.get_historical_close.side_effect = PriceUnavailableError(
        "RHM.DE", "data gap"
    )
    from app.ui.pages.manage import _render_recording_preview

    price_available, deviation_pct = _render_recording_preview(
        ticker="RHM.DE",
        currency=Currency.EUR,
        tx_type="Buy",
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=Decimal("126.49"),
        fees_eur=Decimal("0.99"),
    )

    assert price_available is True
    assert deviation_pct is None
    mock_st.warning.assert_called_once()


@patch("app.ui.pages.manage.get_price_provider")
@patch("app.ui.pages.manage.st")
def test_broad_exception_returns_true_none_and_does_not_raise(
    mock_st: MagicMock, mock_get_price: MagicMock
) -> None:
    # A generic (non-PriceUnavailableError) exception from the price provider
    # must not propagate — returns (True, None) and logs at WARNING.
    mock_get_price.return_value.get_historical_close.side_effect = ValueError("unexpected boom")
    from app.ui.pages.manage import _render_recording_preview

    price_available, deviation_pct = _render_recording_preview(
        ticker="APD",
        currency=Currency.USD,
        tx_type="Buy",
        trade_date=_TRADE_DATE,
        shares=Decimal("1"),
        eur_total=Decimal("300.00"),
        fees_eur=Decimal("0"),
    )

    assert price_available is True
    assert deviation_pct is None
