from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.domain.isin_map import IsinMapDocument, IsinMapping
from app.domain.models import Currency, Money, Transaction
from app.ui.cache_keys import transactions_signature as _transactions_signature
from app.ui.pages.overview import build_name_lookup


def test_transactions_signature_deterministic():
    tx1 = Transaction(
        id=str(uuid4()), ticker="AAPL", type="buy", trade_date=date(2024, 1, 1),
        shares=Decimal("10"), price_native=Money(amount=Decimal("150"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9")
    )
    tx2 = Transaction(
        id=str(uuid4()), ticker="MSFT", type="buy", trade_date=date(2024, 1, 2),
        shares=Decimal("5"), price_native=Money(amount=Decimal("200"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9")
    )
    
    sig1 = _transactions_signature([tx1, tx2])
    sig2 = _transactions_signature([tx1, tx2])
    assert sig1 == sig2
    
    sig3 = _transactions_signature([tx1])
    assert sig1 != sig3

def test_transactions_signature_empty():
    assert _transactions_signature([]) == "empty"

def test_transactions_signature_order_insensitive():
    tx1 = Transaction(
        id=str(uuid4()), ticker="AAPL", type="buy", trade_date=date(2024, 1, 1),
        shares=Decimal("10"), price_native=Money(amount=Decimal("150"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9")
    )
    tx2 = Transaction(
        id=str(uuid4()), ticker="MSFT", type="buy", trade_date=date(2024, 1, 2),
        shares=Decimal("5"), price_native=Money(amount=Decimal("200"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9")
    )
    
    sig1 = _transactions_signature([tx1, tx2])
    sig2 = _transactions_signature([tx2, tx1])
    assert sig1 == sig2


def test_transactions_signature_changes_when_only_a_ticker_is_rewritten():
    """ADR-014: a mapping change rewrites tickers in place, so the key must move."""
    tx = Transaction(
        id=str(uuid4()), ticker="DE000A0F5UF5", type="buy", trade_date=date(2024, 1, 1),
        shares=Decimal("10"), price_native=Money(amount=Decimal("150"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"), isin="DE000A0F5UF5", source="scalable_csv",
    )
    remapped = tx.model_copy(update={"ticker": "EXS1.DE"})

    assert _transactions_signature([tx]) != _transactions_signature([remapped])


# ── build_name_lookup ────────────────────────────────────────────────────────


def _tx(ticker: str, isin: str | None) -> Transaction:
    return Transaction(
        id=str(uuid4()), ticker=ticker, type="buy", trade_date=date(2026, 1, 1),
        shares=Decimal("1"), price_native=Money(amount=Decimal("10"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9"), isin=isin,
    )


def _entry(ticker: str | None, name: str, status: str) -> IsinMapping:
    return IsinMapping(ticker=ticker, name=name, status=status)  # type: ignore[arg-type]


def test_name_lookup_keys_a_mapped_holding_by_its_feed_ticker():
    doc = IsinMapDocument(entries={"US67066G1040": _entry("NVDA", "NVIDIA", "mapped")})
    assert build_name_lookup(doc, [])["NVDA"] == "NVIDIA"


def test_name_lookup_keys_a_no_feed_holding_by_its_isin():
    doc = IsinMapDocument(entries={"DE000HT41XN9": _entry(None, "Apple Short Turbo", "ignored")})
    assert build_name_lookup(doc, [])["DE000HT41XN9"] == "Apple Short Turbo"


def test_name_lookup_bridges_a_ticker_the_map_entry_no_longer_carries():
    """The regression: the book trades ARM, the entry lost its ticker, and the
    Live Overview printed "ARM" in the Name column."""
    doc = IsinMapDocument(entries={"US0420682058": _entry(None, "Arm Holdings", "unmapped")})
    lookup = build_name_lookup(doc, [_tx("ARM", "US0420682058")])
    assert lookup["ARM"] == "Arm Holdings"


def test_name_lookup_leaves_a_ticker_with_no_map_entry_alone():
    lookup = build_name_lookup(IsinMapDocument(), [_tx("FOO", "US0000000000")])
    assert "FOO" not in lookup


def test_name_lookup_prefers_the_map_over_the_book_bridge():
    doc = IsinMapDocument(entries={"US0420682058": _entry("ARM", "Arm Holdings", "mapped")})
    lookup = build_name_lookup(doc, [_tx("ARM", "US0420682058")])
    assert lookup["ARM"] == "Arm Holdings"
