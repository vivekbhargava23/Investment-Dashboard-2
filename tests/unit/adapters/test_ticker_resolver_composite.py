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


# ---------------------------------------------------------------------------
# resolve — primary fills limit
# ---------------------------------------------------------------------------

def test_resolve_primary_fills_limit_skips_fallback() -> None:
    # FakeTickerResolver matches query as substring of symbol/name.
    # Use "CORP" which appears in every _match()'s name ("X Corp").
    primary = FakeTickerResolver([_match("AAPL"), _match("AAON")])
    fallback = FakeTickerResolver([_match("AACG")])
    composite = CompositeTickerResolver(primary=primary, fallbacks=[fallback])

    results = composite.resolve("CORP", limit=2)

    assert fallback.resolve_call_count == 0
    assert len(results) == 2
    assert {r.symbol for r in results} == {"AAPL", "AAON"}


# ---------------------------------------------------------------------------
# resolve — primary short → fallback fills the gap
# ---------------------------------------------------------------------------

def test_resolve_fallback_fills_gap() -> None:
    # "CORP" matches all _match() names ("X Corp"). primary has 3, fallback has 5,
    # limit=8 → all 8 should appear.
    primary = FakeTickerResolver([_match("PA"), _match("PB"), _match("PC")])
    fallback = FakeTickerResolver([
        _match("FA"), _match("FB"), _match("FC"), _match("FD"), _match("FE"),
    ])
    composite = CompositeTickerResolver(primary=primary, fallbacks=[fallback])

    results = composite.resolve("CORP", limit=8)

    assert fallback.resolve_call_count == 1
    assert len(results) == 8
    primary_syms = {"PA", "PB", "PC"}
    for sym in primary_syms:
        assert sym in {r.symbol for r in results}


# ---------------------------------------------------------------------------
# resolve — primary raises → fallback called
# ---------------------------------------------------------------------------

class _RaisingResolver:
    """Resolver that always raises on resolve/lookup."""

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        raise RuntimeError("primary down")

    def lookup(self, symbol: str) -> TickerMatch | None:
        raise RuntimeError("primary down")

    def clear_cache(self) -> None:
        pass


def test_resolve_primary_raises_fallback_called() -> None:
    fallback = FakeTickerResolver([_match("FB")])
    composite = CompositeTickerResolver(primary=_RaisingResolver(), fallbacks=[fallback])

    results = composite.resolve("FB", limit=5)

    assert fallback.resolve_call_count == 1
    assert len(results) == 1
    assert results[0].symbol == "FB"


# ---------------------------------------------------------------------------
# resolve — both raise → returns empty, no exception
# ---------------------------------------------------------------------------

def test_resolve_both_raise_returns_empty() -> None:
    composite = CompositeTickerResolver(
        primary=_RaisingResolver(), fallbacks=[_RaisingResolver()]
    )

    results = composite.resolve("anything", limit=5)

    assert results == []


# ---------------------------------------------------------------------------
# resolve — dedup: primary's version wins
# ---------------------------------------------------------------------------

def test_resolve_dedup_primary_wins() -> None:
    primary_match = TickerMatch(
        symbol="OVERLAP",
        name="Primary Name",
        exchange="NYSE",
        currency=Currency.USD,
        recent_price=None,
    )
    fallback_match = TickerMatch(
        symbol="OVERLAP",
        name="Fallback Name",
        exchange="XETRA",
        currency=Currency.EUR,
        recent_price=None,
    )
    primary = FakeTickerResolver([primary_match])
    fallback = FakeTickerResolver([fallback_match, _match("EXTRA")])
    composite = CompositeTickerResolver(primary=primary, fallbacks=[fallback])

    results = composite.resolve("OVERLAP", limit=5)

    overlap_results = [r for r in results if r.symbol == "OVERLAP"]
    assert len(overlap_results) == 1
    assert overlap_results[0].name == "Primary Name"
    assert overlap_results[0].currency == Currency.USD


# ---------------------------------------------------------------------------
# lookup — primary returns result → fallback not called
# ---------------------------------------------------------------------------

def test_lookup_primary_hit_skips_fallback() -> None:
    primary = FakeTickerResolver([_match("AAPL")])
    fallback = FakeTickerResolver([_match("AAPL")])
    composite = CompositeTickerResolver(primary=primary, fallbacks=[fallback])

    result = composite.lookup("AAPL")

    assert result is not None
    assert result.symbol == "AAPL"
    assert fallback.lookup_call_count == 0


# ---------------------------------------------------------------------------
# lookup — primary returns None → fallback tried
# ---------------------------------------------------------------------------

def test_lookup_primary_miss_falls_back() -> None:
    primary = FakeTickerResolver([])
    fallback = FakeTickerResolver([_match("RHM.DE", Currency.EUR)])
    composite = CompositeTickerResolver(primary=primary, fallbacks=[fallback])

    result = composite.lookup("RHM.DE")

    assert result is not None
    assert result.symbol == "RHM.DE"
    assert fallback.lookup_call_count == 1


# ---------------------------------------------------------------------------
# lookup — primary raises → fallback tried
# ---------------------------------------------------------------------------

def test_lookup_primary_raises_fallback_called() -> None:
    fallback = FakeTickerResolver([_match("FB")])
    composite = CompositeTickerResolver(primary=_RaisingResolver(), fallbacks=[fallback])

    result = composite.lookup("FB")

    assert result is not None
    assert result.symbol == "FB"


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
