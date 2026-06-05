"""
Unit tests for pure helper functions in app.ui.pages.manage.
These do not require a Streamlit context.
"""
from datetime import date
from decimal import Decimal

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.ports.ticker_resolver import TickerMatch
from app.ui.pages.manage import (
    _init_state,
    _match_label,
    _tx_to_form_values,
    build_transactions_dataframe,
    filter_transactions,
)


def _eur_tx(**kwargs) -> Transaction:  # type: ignore[no-untyped-def]
    defaults = dict(
        type=TransactionType.BUY,
        ticker="RHM.DE",
        trade_date=date(2026, 3, 27),
        shares=Decimal("1"),
        price_native=Money(amount=Decimal("1452.75"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )
    defaults.update(kwargs)
    return Transaction(**defaults)


def _usd_tx(**kwargs) -> Transaction:  # type: ignore[no-untyped-def]
    defaults = dict(
        type=TransactionType.BUY,
        ticker="APD",
        trade_date=date(2025, 7, 22),
        shares=Decimal("4"),
        price_native=Money(amount=Decimal("250"), currency=Currency.USD),
        fees_native=Money(amount=Decimal("1.09"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9050"),
    )
    defaults.update(kwargs)
    return Transaction(**defaults)


# ---------------------------------------------------------------------------
# _init_state
# ---------------------------------------------------------------------------

def test_init_state_sets_all_defaults() -> None:
    state: dict = {}
    _init_state(state)
    assert "manage_add_query" in state
    assert "manage_add_resolved" in state
    assert "manage_editing_tx_id" in state
    assert "manage_deleting_tx_ids" in state
    assert "manage_feedback" in state
    assert state["manage_add_query"] == ""
    assert state["manage_add_resolved"] is None
    assert state["manage_feedback"] is None


def test_init_state_is_idempotent() -> None:
    state: dict = {"manage_add_query": "typed_value"}
    _init_state(state)
    _init_state(state)
    assert state["manage_add_query"] == "typed_value"  # not overwritten


def test_init_state_only_fills_missing_keys() -> None:
    state: dict = {"manage_editing_tx_id": "some-id"}
    _init_state(state)
    assert state["manage_editing_tx_id"] == "some-id"  # preserved


# ---------------------------------------------------------------------------
# _tx_to_form_values
# ---------------------------------------------------------------------------

def test_tx_to_form_values_eur_no_fees() -> None:
    tx = _eur_tx()
    vals = _tx_to_form_values(tx)
    assert vals["ticker"] == "RHM.DE"
    assert vals["tx_type"] == "buy"
    assert vals["trade_date"] == date(2026, 3, 27)
    assert abs(vals["shares"] - 1.0) < 1e-6
    # cost_eur = 1452.75 * 1 = 1452.75
    assert abs(vals["eur_total"] - 1452.75) < 0.01
    assert abs(vals["fees_eur"] - 0.0) < 0.01


def test_tx_to_form_values_usd_with_fees() -> None:
    tx = _usd_tx()
    vals = _tx_to_form_values(tx)
    assert vals["ticker"] == "APD"
    assert vals["tx_type"] == "buy"
    # fees_eur = 1.09 * 0.9050 = 0.9865 ≈ 0.99
    assert abs(vals["fees_eur"] - round(1.09 * 0.9050, 2)) < 0.01
    # eur_total = cost_eur = (4 * 250 + 1.09) * 0.9050 = 1001.09 * 0.9050 ≈ 906.0
    expected_total = float((Decimal("4") * Decimal("250") + Decimal("1.09")) * Decimal("0.9050"))
    assert abs(vals["eur_total"] - expected_total) < 0.05


def test_tx_to_form_values_notes_preserved() -> None:
    tx = _eur_tx()
    tx2 = tx.model_copy(update={"notes": "test note"})
    vals = _tx_to_form_values(tx2)
    assert vals["notes"] == "test note"


def test_tx_to_form_values_no_notes_is_empty_string() -> None:
    tx = _eur_tx()
    vals = _tx_to_form_values(tx)
    assert vals["notes"] == ""


# ---------------------------------------------------------------------------
# _match_label
# ---------------------------------------------------------------------------

def test_match_label_no_price() -> None:
    m = TickerMatch(symbol="APD", name="Air Products", exchange="NYSE", currency=Currency.USD)
    label = _match_label(m)
    assert "APD" in label
    assert "Air Products" in label
    assert "NYSE" in label
    assert "USD" in label


def test_match_label_with_price() -> None:
    price = Money(amount=Decimal("298.35"), currency=Currency.USD)
    m = TickerMatch(
        symbol="APD", name="Air Products", exchange="NYSE",
        currency=Currency.USD, recent_price=price,
    )
    label = _match_label(m)
    assert "298" in label


def test_match_label_jpy() -> None:
    m = TickerMatch(
        symbol="5631.T", name="Japan Steel Works", exchange="TYO", currency=Currency.JPY,
    )
    label = _match_label(m)
    assert "5631.T" in label
    assert "JPY" in label


# ---------------------------------------------------------------------------
# TICKET-RD2: build_transactions_dataframe — display rows for the sortable grid
# ---------------------------------------------------------------------------

def test_transactions_dataframe_columns() -> None:
    df = build_transactions_dataframe([_eur_tx()])
    assert list(df.columns) == ["Ticker", "Type", "Date", "Shares", "Cost (€)", "Notes"]


def test_transactions_dataframe_row_order_matches_input() -> None:
    """Row order must equal input order so a selection index maps back to the tx."""
    a = _eur_tx(ticker="AAA.DE", trade_date=date(2024, 1, 1))
    z = _eur_tx(ticker="ZZZ.DE", trade_date=date(2026, 1, 1))
    df = build_transactions_dataframe([z, a])
    assert list(df["Ticker"]) == ["ZZZ.DE", "AAA.DE"]


def test_transactions_dataframe_values() -> None:
    tx = _eur_tx(ticker="RHM.DE", shares=Decimal("3"),
                 price_native=Money(amount=Decimal("100"), currency=Currency.EUR))
    row = build_transactions_dataframe([tx]).iloc[0]
    assert row["Ticker"] == "RHM.DE"
    assert row["Type"] == "BUY"
    assert row["Date"] == tx.trade_date
    assert row["Shares"] == 3.0
    assert row["Cost (€)"] == float(tx.cost_eur.amount)


def test_transactions_dataframe_notes_blank_when_absent() -> None:
    row = build_transactions_dataframe([_eur_tx()]).iloc[0]
    assert row["Notes"] == ""


# ---------------------------------------------------------------------------
# TICKET-RD2: filter_transactions — per-column search for the table
# ---------------------------------------------------------------------------

def _tickers(txs: list[Transaction]) -> list[str]:
    return [t.ticker for t in txs]


def test_filter_ticker_substring_case_insensitive() -> None:
    ase = _eur_tx(ticker="ASE.DE")
    nvda = _usd_tx(ticker="NVDA")
    out = filter_transactions([ase, nvda], ticker_query="ase")
    assert _tickers(out) == ["ASE.DE"]


def test_filter_empty_query_returns_all() -> None:
    txs = [_eur_tx(ticker="ASE.DE"), _usd_tx(ticker="NVDA")]
    assert len(filter_transactions(txs)) == 2


def test_filter_type_buy_only() -> None:
    buy = _eur_tx(ticker="ASE.DE", type=TransactionType.BUY)
    sell = _eur_tx(ticker="ASE.DE", type=TransactionType.SELL, shares=Decimal("1"))
    out = filter_transactions([buy, sell], type_filter="Sell")
    assert out == [sell]


def test_filter_notes_substring() -> None:
    a = _eur_tx(ticker="ASE.DE", notes="rebalance Q1")
    b = _eur_tx(ticker="ASE.DE", notes="dividend reinvest")
    out = filter_transactions([a, b], notes_query="rebalance")
    assert out == [a]


def test_filter_combines_conditions() -> None:
    keep = _eur_tx(ticker="ASE.DE", type=TransactionType.BUY, notes="core")
    wrong_type = _eur_tx(
        ticker="ASE.DE", type=TransactionType.SELL, shares=Decimal("1"), notes="core"
    )
    wrong_ticker = _usd_tx(ticker="NVDA", notes="core")
    out = filter_transactions(
        [keep, wrong_type, wrong_ticker],
        ticker_query="ase",
        type_filter="Buy",
        notes_query="core",
    )
    assert out == [keep]
