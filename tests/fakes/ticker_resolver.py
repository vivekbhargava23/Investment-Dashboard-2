from decimal import Decimal

from app.domain.money import Currency, Money
from app.ports.ticker_resolver import TickerMatch, TickerResolver

FAKE_TICKER_NVDA = TickerMatch(
    symbol="NVDA",
    name="NVIDIA Corporation",
    exchange="NASDAQ",
    currency=Currency.USD,
    recent_price=Money(amount=Decimal("450.00"), currency=Currency.USD),
)

FAKE_TICKER_RHM = TickerMatch(
    symbol="RHM.DE",
    name="Rheinmetall AG",
    exchange="XETRA",
    currency=Currency.EUR,
    recent_price=None,
)


class FakeTickerResolver:
    """
    Fake implementation of TickerResolver for use in unit tests.

    Initialise with a dict mapping symbols to TickerMatch objects.
    `resolve` does a case-insensitive prefix/substring search over
    the symbol and name fields of all registered matches.
    `lookup` does an exact case-insensitive symbol match.
    """

    def __init__(self, matches: list[TickerMatch] | None = None) -> None:
        self._matches: list[TickerMatch] = matches or []
        self._cache_cleared_count = 0
        self.resolve_call_count = 0
        self.lookup_call_count = 0

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        self.resolve_call_count += 1
        query = query.strip().upper()
        if not query:
            return []
        hits = [
            m for m in self._matches
            if query in m.symbol.upper() or query in m.name.upper()
        ]
        return hits[:limit]

    def lookup(self, symbol: str) -> TickerMatch | None:
        self.lookup_call_count += 1
        symbol = symbol.strip().upper()
        for m in self._matches:
            if m.symbol.upper() == symbol:
                return m
        return None

    def clear_cache(self) -> None:
        self._cache_cleared_count += 1

    def add(self, match: TickerMatch) -> None:
        self._matches.append(match)


# Type-check that FakeTickerResolver satisfies the Protocol at import time.
def _type_check() -> None:
    _: TickerResolver = FakeTickerResolver()
