"""Unit tests for CompositeTickerResolver. Zero network access — uses FakeTickerResolver."""
from app.adapters.ticker_resolver_composite.adapter import CompositeTickerResolver
from app.domain.money import Currency
from app.ports.ticker_resolver import TickerMatch
from tests.fakes.ticker_resolver import FakeTickerResolver


def _match(symbol: str, currency: Currency = Currency.USD) -> TickerMatch:
    return TickerMatch(
        symbol=symbol,
        name=f"{symbol} Corp",
        exchange="TEST",
        currency=currency,
        recent_price=None,
    )


class _RaisingResolver:
    """Resolver that always raises."""

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        raise RuntimeError("source down")

    def lookup(self, symbol: str) -> TickerMatch | None:
        raise RuntimeError("source down")

    def clear_cache(self) -> None:
        pass


# ---------------------------------------------------------------------------
# resolve — primary returns limit → fallback never called
# ---------------------------------------------------------------------------

def test_resolve_primary_fills_limit_skips_fallback() -> None:
    # FakeTickerResolver matches query as substring of name ("X Corp").
    # "CORP" appears in every _match() name so all symbols match.
    primary = FakeTickerResolver([_match("AAPL"), _match("AAON")])
    fallback = FakeTickerResolver([_match("AACG")])
    composite = CompositeTickerResolver(primary=primary, fallbacks=[fallback])

    results = composite.resolve("CORP", limit=2)

    assert fallback.resolve_call_count == 0
    assert len(results) == 2
    assert {r.symbol for r in results} == {"AAPL", "AAON"}


# ---------------------------------------------------------------------------
# resolve — primary returns < limit → fallback fills the gap
# ---------------------------------------------------------------------------

def test_resolve_fallback_fills_gap() -> None:
    primary = FakeTickerResolver([_match("PA"), _match("PB"), _match("PC")])
    fallback = FakeTickerResolver([
        _match("FA"), _match("FB"), _match("FC"), _match("FD"), _match("FE"),
    ])
    composite = CompositeTickerResolver(primary=primary, fallbacks=[fallback])

    results = composite.resolve("CORP", limit=8)

    assert fallback.resolve_call_count == 1
    assert len(results) == 8
    for sym in {"PA", "PB", "PC"}:
        assert sym in {r.symbol for r in results}


# ---------------------------------------------------------------------------
# resolve — primary raises → fallback is called
# ---------------------------------------------------------------------------

def test_resolve_primary_raises_fallback_called() -> None:
    fallback = FakeTickerResolver([_match("FB")])
    composite = CompositeTickerResolver(primary=_RaisingResolver(), fallbacks=[fallback])

    results = composite.resolve("CORP", limit=5)

    assert fallback.resolve_call_count == 1
    assert results[0].symbol == "FB"


# ---------------------------------------------------------------------------
# resolve — both raise → returns empty list, no exception
# ---------------------------------------------------------------------------

def test_resolve_both_raise_returns_empty() -> None:
    composite = CompositeTickerResolver(
        primary=_RaisingResolver(), fallbacks=[_RaisingResolver()]
    )

    assert composite.resolve("anything", limit=5) == []


# ---------------------------------------------------------------------------
# resolve — dedup: primary's version wins when same symbol in both
# ---------------------------------------------------------------------------

def test_resolve_dedup_primary_wins() -> None:
    # Both matches must contain "CORP" in their name so FakeTickerResolver returns them.
    primary_match = TickerMatch(
        symbol="OVERLAP",
        name="OVERLAP Corp Primary",
        exchange="NYSE",
        currency=Currency.USD,
        recent_price=None,
    )
    fallback_match = TickerMatch(
        symbol="OVERLAP",
        name="OVERLAP Corp Fallback",
        exchange="XETRA",
        currency=Currency.EUR,
        recent_price=None,
    )
    primary = FakeTickerResolver([primary_match])
    fallback = FakeTickerResolver([fallback_match, _match("EXTRA")])
    composite = CompositeTickerResolver(primary=primary, fallbacks=[fallback])

    results = composite.resolve("CORP", limit=5)

    overlap = [r for r in results if r.symbol == "OVERLAP"]
    assert len(overlap) == 1
    assert overlap[0].name == "OVERLAP Corp Primary"
    assert overlap[0].currency == Currency.USD


# ---------------------------------------------------------------------------
# lookup — primary returns result → fallback not called
# ---------------------------------------------------------------------------

def test_lookup_primary_hit_skips_fallback() -> None:
    primary = FakeTickerResolver([_match("AAPL")])
    fallback = FakeTickerResolver([_match("AAPL")])
    composite = CompositeTickerResolver(primary=primary, fallbacks=[fallback])

    result = composite.lookup("AAPL")

    assert result is not None and result.symbol == "AAPL"
    assert fallback.lookup_call_count == 0


# ---------------------------------------------------------------------------
# lookup — primary returns None → fallback tried
# ---------------------------------------------------------------------------

def test_lookup_primary_miss_falls_back() -> None:
    primary = FakeTickerResolver([])
    fallback = FakeTickerResolver([_match("RHM.DE", Currency.EUR)])
    composite = CompositeTickerResolver(primary=primary, fallbacks=[fallback])

    result = composite.lookup("RHM.DE")

    assert result is not None and result.symbol == "RHM.DE"
    assert fallback.lookup_call_count == 1


# ---------------------------------------------------------------------------
# lookup — primary raises → fallback tried
# ---------------------------------------------------------------------------

def test_lookup_primary_raises_fallback_called() -> None:
    fallback = FakeTickerResolver([_match("FB")])
    composite = CompositeTickerResolver(primary=_RaisingResolver(), fallbacks=[fallback])

    result = composite.lookup("FB")

    assert result is not None and result.symbol == "FB"


# ---------------------------------------------------------------------------
# lookup — both return None → returns None
# ---------------------------------------------------------------------------

def test_lookup_both_none_returns_none() -> None:
    composite = CompositeTickerResolver(
        primary=FakeTickerResolver([]), fallbacks=[FakeTickerResolver([])]
    )
    assert composite.lookup("UNKNOWN") is None


# ---------------------------------------------------------------------------
# lookup — both raise → returns None, no exception
# ---------------------------------------------------------------------------

def test_lookup_both_raise_returns_none() -> None:
    composite = CompositeTickerResolver(
        primary=_RaisingResolver(), fallbacks=[_RaisingResolver()]
    )
    assert composite.lookup("ANYTHING") is None


# ---------------------------------------------------------------------------
# clear_cache — propagated to all adapters
# ---------------------------------------------------------------------------

def test_clear_cache_propagates_to_all() -> None:
    primary = FakeTickerResolver([])
    fallback1 = FakeTickerResolver([])
    fallback2 = FakeTickerResolver([])
    composite = CompositeTickerResolver(primary=primary, fallbacks=[fallback1, fallback2])

    composite.clear_cache()

    assert primary._cache_cleared_count == 1
    assert fallback1._cache_cleared_count == 1
    assert fallback2._cache_cleared_count == 1
