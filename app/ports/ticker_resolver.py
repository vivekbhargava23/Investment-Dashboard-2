from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.domain.money import Currency, Money


class TickerMatch(BaseModel):
    """Immutable metadata for a single ticker search result."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    exchange: str
    currency: Currency
    recent_price: Money | None = None


class TickerResolver(Protocol):
    """Contract for fuzzy ticker search and exact-symbol lookup."""

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        """
        Fuzzy/prefix search for tickers matching *query*.

        Returns an empty list when no matches are found or the query is empty.
        Never raises on "no results" — that is a normal outcome.
        Matches whose native currency is not yet in the Currency enum are omitted
        silently rather than causing an exception.
        """
        ...

    def lookup(self, symbol: str) -> TickerMatch | None:
        """
        Exact-symbol lookup. Returns None if the symbol is unknown.
        Used when we already know the symbol and only want metadata.
        """
        ...

    def clear_cache(self) -> None:
        """Invalidate all cached resolver results."""
        ...
