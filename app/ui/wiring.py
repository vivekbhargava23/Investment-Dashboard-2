from functools import lru_cache
from pathlib import Path

from app.adapters.repo_json import JsonTransactionRepository
from app.adapters.repo_json.tax_profile_repo import JsonTaxProfileRepository
from app.adapters.yfinance_feed import YfinanceAdapter
from app.config import get_settings
from app.ports.fx_feed import FxProvider
from app.ports.market_data import OhlcDataProvider
from app.ports.price_feed import PriceProvider
from app.ports.repository import TransactionRepository
from app.ports.tax_profile_repo import TaxProfileRepository
from app.ports.ticker_resolver import TickerResolver


@lru_cache(maxsize=1)
def get_repository() -> TransactionRepository:
    settings = get_settings()
    return JsonTransactionRepository(Path(settings.portfolio_json_path))


@lru_cache(maxsize=1)
def get_tax_profile_repo() -> TaxProfileRepository:
    settings = get_settings()
    return JsonTaxProfileRepository(Path(settings.tax_profile_json_path))


@lru_cache(maxsize=1)
def get_price_provider() -> PriceProvider:
    return YfinanceAdapter()


@lru_cache(maxsize=1)
def get_fx_provider() -> FxProvider:
    # Same instance; YfinanceAdapter implements PriceProvider, FxProvider, and TickerResolver.
    return get_price_provider()  # type: ignore[return-value]


@lru_cache(maxsize=1)
def get_ticker_resolver() -> TickerResolver:
    from typing import cast

    from app.adapters.ticker_resolver_cached import CachedTickerResolver

    settings = get_settings()
    inner = cast(TickerResolver, get_price_provider())
    return CachedTickerResolver(inner=inner, cache_path=settings.ticker_cache_json_path)


@lru_cache(maxsize=1)
def get_ohlc_data_provider() -> OhlcDataProvider:
    from typing import cast

    return cast(OhlcDataProvider, get_price_provider())
