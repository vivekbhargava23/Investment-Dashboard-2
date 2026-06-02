"""
Transaction-building pipeline (EUR-native input model, ADR-005).

build_transaction() converts what the user sees on their broker confirmation
(EUR total debited, shares, fees) into a fully-populated Transaction with the
correct native price, FX rate, and fees in native currency.

This module is pure: no I/O, no Streamlit.  Tests live in
tests/unit/ui/test_manage_form_pipeline.py.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ports.fx_feed import FxRateUnavailableError, HistoricalFxProvider
from app.ports.price_feed import PriceProvider

_SIX_DP = Decimal("0.000001")
_FOUR_DP = Decimal("0.0001")
_TWO_DP = Decimal("0.01")


def build_transaction(
    ticker: str,
    tx_type: TransactionType,
    trade_date: date,
    shares: Decimal,
    eur_total: Decimal,
    fees_eur: Decimal,
    currency: Currency,
    price_provider: PriceProvider,
    fx_provider: HistoricalFxProvider,
) -> tuple[Transaction, Decimal | None]:
    """
    Construct a Transaction from EUR-native broker inputs.

    Parameters
    ----------
    ticker       : canonical symbol, e.g. "APD" or "5631.T"
    tx_type      : BUY or SELL
    trade_date   : date of the fill
    shares       : number of shares (positive)
    eur_total    : total EUR debited / credited on the broker confirmation
                   (includes fees)
    fees_eur     : broker commission in EUR (default 0.99 on Scalable)
    currency     : native trading currency of the ticker
    price_provider: used for historical close (non-EUR tickers only)
    fx_provider  : used for ECB deviation check (non-EUR tickers only)

    Returns
    -------
    (transaction, deviation_pct)
        deviation_pct is None for EUR-native securities.
        It is the % difference between the implied FX rate (derived from the
        user's EUR total) and the ECB historical rate for the trade date.
        A value > 2 should trigger a UI warning.

    Raises
    ------
    PriceUnavailableError
        If the historical native-currency close cannot be fetched.  The UI
        catches this and switches the form to manual-entry fallback mode.
    """
    net_eur = eur_total - fees_eur

    if currency == Currency.EUR:
        price_per_share = (net_eur / shares).quantize(_FOUR_DP, rounding=ROUND_HALF_UP)
        price_native = Money(amount=price_per_share, currency=Currency.EUR)
        fees_native = (
            Money(amount=fees_eur.quantize(_FOUR_DP), currency=Currency.EUR)
            if fees_eur
            else None
        )
        return (
            Transaction(
                ticker=ticker,
                type=tx_type,
                trade_date=trade_date,
                shares=shares,
                price_native=price_native,
                fees_native=fees_native,
                fx_rate_eur=Decimal("1"),
            ),
            None,
        )

    # Non-EUR: fetch historical close and back-compute FX
    historical_close = price_provider.get_historical_close(ticker, trade_date)
    price_native = historical_close

    implied_fx = (net_eur / (shares * historical_close.amount)).quantize(
        _SIX_DP, rounding=ROUND_HALF_UP
    )

    fees_native_nonfx: Money | None = None
    if fees_eur:
        fees_native_amount = (fees_eur / implied_fx).quantize(_FOUR_DP, rounding=ROUND_HALF_UP)
        fees_native_nonfx = Money(amount=fees_native_amount, currency=currency)

    # Deviation check against ECB historical rate
    deviation_pct: Decimal | None = None
    try:
        ecb_fx = fx_provider.get_historical_rate(currency, Currency.EUR, trade_date)
        deviation_pct = (
            abs(implied_fx - ecb_fx) / ecb_fx * Decimal("100")
        ).quantize(_TWO_DP, rounding=ROUND_HALF_UP)
    except FxRateUnavailableError:
        pass  # Deviation check is informational; failure is non-fatal

    return (
        Transaction(
            ticker=ticker,
            type=tx_type,
            trade_date=trade_date,
            shares=shares,
            price_native=price_native,
            fees_native=fees_native_nonfx,
            fx_rate_eur=implied_fx,
        ),
        deviation_pct,
    )
