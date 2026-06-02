from __future__ import annotations

import logging
import os
from pathlib import Path

from app.adapters.ticker_resolver_cached import CachedTickerResolver
from app.adapters.ticker_resolver_composite.adapter import CompositeTickerResolver
from app.adapters.yfinance_resolver.adapter import YfinanceResolverAdapter
from app.ports.ticker_resolver import TickerResolver

_log = logging.getLogger(__name__)


def build_ticker_resolver(
    cache_path: Path,
    finnhub_api_key: str | None = None,
) -> TickerResolver:
    """Build the production TickerResolver: cache(composite(yfinance, [finnhub]))."""
    if finnhub_api_key is None:
        finnhub_api_key = os.environ.get("FINNHUB_API_KEY") or ""

    primary = YfinanceResolverAdapter()
    fallbacks: list[TickerResolver] = []

    if finnhub_api_key:
        from app.adapters.ticker_resolver_finnhub.adapter import FinnhubTickerResolverAdapter

        fallbacks.append(FinnhubTickerResolverAdapter(api_key=finnhub_api_key))
    else:
        _log.info("FINNHUB_API_KEY not set; ticker resolver limited to yfinance")

    composite = CompositeTickerResolver(primary=primary, fallbacks=fallbacks)
    return CachedTickerResolver(inner=composite, cache_path=cache_path)
