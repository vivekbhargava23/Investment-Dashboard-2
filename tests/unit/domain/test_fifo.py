from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.fifo import SellExceedsOpenSharesError, compute_positions, compute_realised_gains
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money

# --- Helpers ---


def _buy(
    ticker: str,
    dt: date,
    shares: Decimal,
    price: Decimal,
    currency: Currency = Currency.EUR,
    fx: Decimal = Decimal("1"),
    tx_id: str | None = None,
) -> Transaction:
    params = {
        "type": TransactionType.BUY,
        "ticker": ticker,
        "trade_date": dt,
        "shares": shares,
        "price_native": Money(amount=price, currency=currency),
        "fx_rate_eur": fx,
    }
    if tx_id:
        params["id"] = tx_id
    return Transaction(**params)


def _sell(
    ticker: str,
    dt: date,
    shares: Decimal,
    price: Decimal,
    currency: Currency = Currency.EUR,
    fx: Decimal = Decimal("1"),
    tx_id: str | None = None,
) -> Transaction:
    params = {
        "type": TransactionType.SELL,
        "ticker": ticker,
        "trade_date": dt,
        "shares": shares,
        "price_native": Money(amount=price, currency=currency),
        "fx_rate_eur": fx,
    }
    if tx_id:
        params["id"] = tx_id
    return Transaction(**params)


# --- Tests ---


def test_empty_input():
    assert compute_positions([], date(2024, 1, 1)) == {}
    assert compute_realised_gains([]) == []


def test_single_buy():
    tx = _buy("SAP.DE", date(2024, 1, 1), Decimal("10"), Decimal("150"))
    positions = compute_positions([tx], date(2024, 1, 1))

    assert len(positions) == 1
    pos = positions["SAP.DE"]
    assert pos.open_shares == Decimal("10")
    assert len(pos.open_lots) == 1
    assert pos.open_lots[0].source_transaction_id == tx.id
    assert pos.cost_basis_eur == Money(amount=Decimal("1500"), currency=Currency.EUR)
    assert pos.realised_gain_eur_ytd == Money.zero(Currency.EUR)


def test_single_buy_full_sell():
    tx1 = _buy(
        "NVDA", date(2024, 1, 1), Decimal("10"), Decimal("100"), Currency.USD, Decimal("1.0")
    )
    tx2 = _sell(
        "NVDA", date(2024, 2, 1), Decimal("10"), Decimal("120"), Currency.USD, Decimal("1.0")
    )

    positions = compute_positions([tx1, tx2], date(2024, 2, 1))
    assert positions == {}

    gains = compute_realised_gains([tx1, tx2])
    assert len(gains) == 1
    assert gains[0].realised_gain_eur == Money(amount=Decimal("200"), currency=Currency.EUR)
    assert gains[0].shares == Decimal("10")


def test_single_buy_partial_sell():
    tx1 = _buy(
        "NVDA", date(2024, 1, 1), Decimal("10"), Decimal("100"), Currency.USD, Decimal("1.0")
    )
    tx2 = _sell(
        "NVDA", date(2024, 2, 1), Decimal("4"), Decimal("120"), Currency.USD, Decimal("1.0")
    )

    positions = compute_positions([tx1, tx2], date(2024, 2, 1))
    pos = positions["NVDA"]
    assert pos.open_shares == Decimal("6")
    assert len(pos.open_lots) == 1
    assert pos.open_lots[0].remaining_shares == Decimal("6")

    gains = compute_realised_gains([tx1, tx2])
    assert len(gains) == 1
    assert gains[0].shares == Decimal("4")
    assert gains[0].realised_gain_eur == Money(amount=Decimal("80"), currency=Currency.EUR)


def test_multiple_buys_partial_sell_crossing_lots():
    tx1 = _buy(
        "NVDA", date(2024, 1, 1), Decimal("10"), Decimal("100"), Currency.USD, Decimal("1.0"), "tx1"
    )
    tx2 = _buy(
        "NVDA", date(2024, 1, 2), Decimal("5"), Decimal("120"), Currency.USD, Decimal("1.0"), "tx2"
    )
    tx3 = _sell(
        "NVDA", date(2024, 2, 1), Decimal("12"), Decimal("130"), Currency.USD, Decimal("1.0"), "tx3"
    )

    positions = compute_positions([tx1, tx2, tx3], date(2024, 2, 1))
    pos = positions["NVDA"]
    assert pos.open_shares == Decimal("3")
    assert len(pos.open_lots) == 1
    assert pos.open_lots[0].source_transaction_id == "tx2"
    assert pos.open_lots[0].remaining_shares == Decimal("3")

    gains = compute_realised_gains([tx1, tx2, tx3])
    assert len(gains) == 2
    # From lot 1: 10 shares * (130-100) = 300
    assert gains[0].buy_transaction_id == "tx1"
    assert gains[0].shares == Decimal("10")
    assert gains[0].realised_gain_eur == Money(amount=Decimal("300"), currency=Currency.EUR)
    # From lot 2: 2 shares * (130-120) = 20
    assert gains[1].buy_transaction_id == "tx2"
    assert gains[1].shares == Decimal("2")
    assert gains[1].realised_gain_eur == Money(amount=Decimal("20"), currency=Currency.EUR)


def test_multi_ticker_no_interference():
    tx1 = _buy("NVDA.DE", date(2024, 1, 1), Decimal("10"), Decimal("100"))
    tx2 = _buy("SAP.DE", date(2024, 1, 1), Decimal("10"), Decimal("150"))

    positions = compute_positions([tx1, tx2], date(2024, 1, 1))
    assert len(positions) == 2
    assert positions["NVDA.DE"].open_shares == Decimal("10")
    assert positions["SAP.DE"].open_shares == Decimal("10")


def test_fx_correctness():
    # USD buy, EUR sell (USD prices same, but FX rate changes)
    # buy 10 NVDA at $100 with fx_rate 0.90 (cost €900)
    tx1 = _buy(
        "NVDA", date(2024, 1, 1), Decimal("10"), Decimal("100"), Currency.USD, Decimal("0.90")
    )
    # sell 10 NVDA at $100 with fx_rate 1.10 (proceeds €1100)
    tx2 = _sell(
        "NVDA", date(2024, 2, 1), Decimal("10"), Decimal("100"), Currency.USD, Decimal("1.10")
    )

    gains = compute_realised_gains([tx1, tx2])
    # Realised gain in EUR = 1100 - 900 = 200
    assert gains[0].realised_gain_eur == Money(amount=Decimal("200"), currency=Currency.EUR)


def test_tie_breaking_by_id():
    # Same date, same ticker, same type
    tx1 = _buy("SAP.DE", date(2024, 1, 1), Decimal("10"), Decimal("100"), tx_id="aaa")
    tx2 = _buy("SAP.DE", date(2024, 1, 1), Decimal("10"), Decimal("110"), tx_id="bbb")
    tx3 = _sell("SAP.DE", date(2024, 2, 1), Decimal("5"), Decimal("120"))

    gains = compute_realised_gains([tx1, tx2, tx3])
    # Should consume from tx1 because "aaa" < "bbb"
    assert gains[0].buy_transaction_id == "aaa"


def test_same_day_buy_then_sell():
    tx1 = _sell("SAP.DE", date(2024, 1, 1), Decimal("10"), Decimal("120"))
    tx2 = _buy("SAP.DE", date(2024, 1, 1), Decimal("10"), Decimal("100"))

    # Even if constructed/sorted SELL before BUY in the input list,
    # compute_positions should process BUY before SELL on the same day.
    positions = compute_positions([tx1, tx2], date(2024, 1, 1))
    assert positions == {}

    gains = compute_realised_gains([tx1, tx2])
    assert len(gains) == 1
    assert gains[0].realised_gain_eur == Money(amount=Decimal("200"), currency=Currency.EUR)


def test_error_sell_exceeds_open():
    tx1 = _buy("SAP.DE", date(2024, 1, 1), Decimal("5"), Decimal("100"), tx_id="buy1")
    tx2 = _sell("SAP.DE", date(2024, 2, 1), Decimal("10"), Decimal("120"), tx_id="sell1")

    with pytest.raises(SellExceedsOpenSharesError) as excinfo:
        compute_positions([tx1, tx2], date(2024, 2, 1))

    msg = str(excinfo.value)
    assert "Sell of 10 SAP.DE on 2024-02-01" in msg
    assert "exceeds open position of 5 shares" in msg
    assert "transaction sell1" in msg


def test_ytd_realised_gain():
    tx1 = _buy("SAP.DE", date(2023, 1, 1), Decimal("15"), Decimal("100"))
    tx2 = _sell("SAP.DE", date(2023, 2, 1), Decimal("5"), Decimal("120"))  # 5*20=100 gain 2023
    tx3 = _sell("SAP.DE", date(2024, 2, 1), Decimal("5"), Decimal("130"))  # 5*30=150 gain 2024

    positions = compute_positions([tx1, tx2, tx3], date(2024, 2, 1))
    pos = positions["SAP.DE"]
    # YTD should only be 150 because as_of is in 2024
    assert pos.realised_gain_eur_ytd == Money(amount=Decimal("150"), currency=Currency.EUR)
    assert pos.open_shares == Decimal("5")


def test_ytd_filter_uses_as_of_year_not_latest_trade_year():
    # Regression for TICKET-TAX-2: YTD must follow as_of.year, not the latest
    # trade year in the data. On main this returned €100; it must be €0.
    tx1 = _buy("SAP.DE", date(2025, 3, 1), Decimal("10"), Decimal("100"))
    tx2 = _sell("SAP.DE", date(2025, 11, 1), Decimal("5"), Decimal("120"))  # €100 gain in 2025

    positions = compute_positions([tx1, tx2], date(2026, 6, 7))
    pos = positions["SAP.DE"]
    # 2025's gain is NOT YTD when as_of is in 2026.
    assert pos.realised_gain_eur_ytd == Money.zero(Currency.EUR)


def test_ytd_includes_only_current_year_realised_gains():
    tx1 = _buy("SAP.DE", date(2024, 3, 1), Decimal("20"), Decimal("100"))
    tx2 = _sell("SAP.DE", date(2025, 4, 1), Decimal("5"), Decimal("110"))  # €50 gain in 2025
    tx3 = _sell("SAP.DE", date(2026, 4, 1), Decimal("5"), Decimal("120"))  # €100 gain in 2026

    positions = compute_positions([tx1, tx2, tx3], date(2026, 6, 7))
    pos = positions["SAP.DE"]
    # 2025's €50 is excluded; only 2026's €100 counts.
    assert pos.realised_gain_eur_ytd == Money(amount=Decimal("100"), currency=Currency.EUR)


def test_empty_transactions_with_as_of_returns_empty_dict():
    assert compute_positions([], date(2026, 6, 7)) == {}


def test_position_with_no_sells_has_zero_ytd_in_current_year():
    tx = _buy("SAP.DE", date(2025, 5, 1), Decimal("10"), Decimal("100"))
    positions = compute_positions([tx], date(2026, 6, 7))
    assert positions["SAP.DE"].realised_gain_eur_ytd == Money.zero(Currency.EUR)


def test_determinism():
    txs = [
        _buy("RHM.DE", date(2024, 1, 1), Decimal("10"), Decimal("100"), tx_id="1"),
        _buy("RHM.DE", date(2024, 1, 1), Decimal("10"), Decimal("110"), tx_id="2"),
        _sell("RHM.DE", date(2024, 2, 1), Decimal("5"), Decimal("120"), tx_id="3"),
        _buy("SAP.DE", date(2024, 1, 1), Decimal("10"), Decimal("150"), tx_id="4"),
    ]

    res1 = compute_positions(txs, date(2024, 2, 1))

    import random

    txs_shuffled = txs[:]
    random.shuffle(txs_shuffled)
    res2 = compute_positions(txs_shuffled, date(2024, 2, 1))

    assert res1 == res2


# --- Property-based Test ---


@st.composite
def valid_transaction_sequence(draw):
    num_tickers = draw(st.integers(min_value=1, max_value=3))
    tickers = [f"TICKER{i}.DE" for i in range(num_tickers)]

    num_txs = draw(st.integers(min_value=1, max_value=15))
    transactions = []

    ticker_shares = {t: Decimal("0") for t in tickers}
    current_date = date(2024, 1, 1)

    for i in range(num_txs):
        ticker = draw(st.sampled_from(tickers))
        # Increment date occasionally
        if draw(st.booleans()):
            current_date = date(2024, 1, current_date.day + 1 if current_date.day < 28 else 1)

        # If we have shares, we can sell. Otherwise we must buy.
        can_sell = ticker_shares[ticker] > 0
        tx_type = draw(
            st.sampled_from(
                [TransactionType.BUY, TransactionType.SELL]
                if can_sell
                else [TransactionType.BUY]
            )
        )

        shares = draw(st.decimals(min_value=Decimal("0.0001"), max_value=Decimal("100"), places=4))
        if tx_type == TransactionType.SELL:
            shares = min(shares, ticker_shares[ticker])
            ticker_shares[ticker] -= shares
            transactions.append(_sell(ticker, current_date, shares, Decimal("100"), tx_id=f"tx{i}"))
        else:
            ticker_shares[ticker] += shares
            transactions.append(_buy(ticker, current_date, shares, Decimal("100"), tx_id=f"tx{i}"))

    return transactions


@given(transactions=valid_transaction_sequence())
def test_fifo_shares_consistency_property(transactions):
    gains = compute_realised_gains(transactions)

    # For each ticker, sum of RealisedGain.shares should equal sum of SELL transaction shares
    for ticker in {tx.ticker for tx in transactions}:
        sell_tx_shares = sum(
            (
                tx.shares
                for tx in transactions
                if tx.ticker == ticker and tx.type == TransactionType.SELL
            ),
            Decimal("0"),
        )
        realised_gain_shares = sum(
            (gain.shares for gain in gains if gain.ticker == ticker), Decimal("0")
        )

        assert realised_gain_shares.quantize(Decimal("0.0001")) == sell_tx_shares.quantize(
            Decimal("0.0001")
        )
