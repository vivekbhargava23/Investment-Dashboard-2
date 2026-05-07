"""End-to-end integration test for CachedTickerResolver. Requires --run-integration flag."""
import time

import pytest

from app.adapters.ticker_resolver_cached import CachedTickerResolver
from app.adapters.yfinance_feed import YfinanceAdapter
from app.domain.money import Currency


@pytest.mark.integration
def test_cache_primes_and_serves_from_disk(tmp_path):
    """Resolve from network, persist to disk, then reload and serve from disk under 50ms."""
    live_adapter = YfinanceAdapter()
    cache_file = tmp_path / "ticker_cache.json"

    cached = CachedTickerResolver(inner=live_adapter, cache_path=cache_file)
    results = cached.resolve("APD")

    assert len(results) > 0
    apd_matches = [r for r in results if r.symbol == "APD"]
    assert apd_matches, f"Expected APD in results, got: {[r.symbol for r in results]}"
    assert apd_matches[0].currency == Currency.USD

    # Reload from disk — should be a fast cache hit
    blank_inner = YfinanceAdapter()
    cached2 = CachedTickerResolver(inner=blank_inner, cache_path=cache_file)

    start = time.perf_counter()
    results2 = cached2.resolve("APD")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 50, f"Disk cache hit took {elapsed_ms:.1f}ms, expected < 50ms"
    assert [r.symbol for r in results2] == [r.symbol for r in results]
