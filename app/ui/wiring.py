from functools import lru_cache
from pathlib import Path

import streamlit as st

from app.adapters.company_factory import build_company_provider
from app.adapters.fx_ecb import EcbFxAdapter
from app.adapters.fx_yfinance import YfinanceLiveFxAdapter
from app.adapters.isin_map.repo import JsonIsinMapRepository
from app.adapters.repo_json import JsonNavSnapshotRepository, JsonTransactionRepository
from app.adapters.repo_json.tax_profile_repo import JsonTaxProfileRepository
from app.adapters.ticker_resolver_cached import CachedTickerResolver
from app.adapters.yfinance_ohlc import YfinanceOhlcAdapter
from app.adapters.yfinance_price import YfinancePriceAdapter
from app.adapters.yfinance_resolver import YfinanceResolverAdapter
from app.config import get_settings
from app.ports.company_data import CompanyDataProvider
from app.ports.fx_feed import FxProvider, HistoricalFxProvider, LiveFxProvider
from app.ports.isin_map import IsinMapRepository
from app.ports.market_data import OhlcDataProvider
from app.ports.nav_repository import NavSnapshotRepository
from app.ports.price_feed import PriceProvider
from app.ports.repository import TransactionRepository
from app.ports.tax_profile_repo import TaxProfileRepository
from app.ports.ticker_resolver import TickerResolver


@lru_cache(maxsize=1)
def get_nav_snapshot_repo() -> NavSnapshotRepository:
    settings = get_settings()
    return JsonNavSnapshotRepository(settings.nav_snapshots_json_path)


@lru_cache(maxsize=1)
def get_repository() -> TransactionRepository:
    settings = get_settings()
    return JsonTransactionRepository(
        Path(settings.portfolio_json_path),
        nav_repo=get_nav_snapshot_repo(),
    )


@lru_cache(maxsize=1)
def get_tax_profile_repo() -> TaxProfileRepository:
    settings = get_settings()
    return JsonTaxProfileRepository(Path(settings.tax_profile_json_path))


@lru_cache(maxsize=1)
def get_price_provider() -> PriceProvider:
    return YfinancePriceAdapter()


@lru_cache(maxsize=1)
def get_historical_fx_provider() -> HistoricalFxProvider:
    settings = get_settings()
    return EcbFxAdapter(cache_path=settings.fx_cache_dir / "ecb.json")


@lru_cache(maxsize=1)
def get_live_fx_provider() -> LiveFxProvider:
    return YfinanceLiveFxAdapter()


@lru_cache(maxsize=1)
def get_fx_provider() -> FxProvider:
    """Back-compat shim. Prefer get_live_fx_provider() or get_historical_fx_provider()."""
    return YfinanceLiveFxAdapter()


@lru_cache(maxsize=1)
def get_ticker_resolver() -> TickerResolver:
    settings = get_settings()
    return CachedTickerResolver(
        inner=YfinanceResolverAdapter(),
        cache_path=settings.ticker_cache_json_path,
    )


@lru_cache(maxsize=1)
def get_ohlc_data_provider() -> OhlcDataProvider:
    return YfinanceOhlcAdapter()


@lru_cache(maxsize=1)
def get_isin_map_repo() -> IsinMapRepository:
    settings = get_settings()
    return JsonIsinMapRepository(settings.isin_map_json_path)


@st.cache_resource
def get_company_provider() -> CompanyDataProvider:
    return build_company_provider()
