"""Unit tests for the TickerMatch model and TickerResolver protocol shape."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.money import Currency, Money
from app.ports.ticker_resolver import TickerMatch, TickerResolver
from tests.fakes.ticker_resolver import FakeTickerResolver


def _make_match(**kwargs) -> TickerMatch:  # type: ignore[no-untyped-def]
    defaults = dict(
        symbol="APD",
        name="Air Products and Chemicals",
        exchange="NYSE",
        currency=Currency.USD,
        recent_price=None,
    )
    defaults.update(kwargs)
    return TickerMatch(**defaults)


def test_ticker_match_constructs():
    m = _make_match()
    assert m.symbol == "APD"
    assert m.currency == Currency.USD
    assert m.recent_price is None


def test_ticker_match_with_price():
    price = Money(amount=Decimal("255.30"), currency=Currency.USD)
    m = _make_match(recent_price=price)
    assert m.recent_price == price


def test_ticker_match_is_frozen():
    m = _make_match()
    with pytest.raises(ValidationError):
        m.symbol = "CHANGED"  # type: ignore[misc]


def test_ticker_match_jpy():
    m = _make_match(
        symbol="5631.T",
        name="Japan Steel Works",
        exchange="TYO",
        currency=Currency.JPY,
        recent_price=Money(amount=Decimal("9049"), currency=Currency.JPY),
    )
    assert m.currency == Currency.JPY


def test_ticker_match_eur():
    m = _make_match(symbol="RHM.DE", exchange="XETRA", currency=Currency.EUR)
    assert m.currency == Currency.EUR


def test_fake_resolver_satisfies_protocol():
    resolver: TickerResolver = FakeTickerResolver()
    assert callable(resolver.resolve)
    assert callable(resolver.lookup)
    assert callable(resolver.clear_cache)


def test_fake_resolver_resolve_prefix():
    apd = _make_match(symbol="APD", name="Air Products")
    nvda = _make_match(symbol="NVDA", name="NVIDIA Corporation", currency=Currency.USD)
    r = FakeTickerResolver([apd, nvda])
    hits = r.resolve("AIR")  # matches "Air Products" but not "NVIDIA"
    assert apd in hits
    assert nvda not in hits


def test_fake_resolver_resolve_empty_query():
    r = FakeTickerResolver([_make_match()])
    assert r.resolve("") == []


def test_fake_resolver_lookup_hit():
    m = _make_match()
    r = FakeTickerResolver([m])
    found = r.lookup("APD")
    assert found == m


def test_fake_resolver_lookup_miss():
    r = FakeTickerResolver([_make_match()])
    assert r.lookup("UNKNOWN") is None


def test_fake_resolver_lookup_case_insensitive():
    m = _make_match()
    r = FakeTickerResolver([m])
    assert r.lookup("apd") == m


def test_fake_resolver_clear_cache():
    r = FakeTickerResolver()
    r.clear_cache()
    assert r._cache_cleared_count == 1
