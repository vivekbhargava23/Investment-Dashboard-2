from pathlib import Path

import streamlit as st

from app.adapters.catalysts.repo import JsonCatalystsRepository
from app.adapters.company_factory import build_company_provider
from app.adapters.fx_ecb import EcbFxAdapter
from app.adapters.fx_yfinance import YfinanceLiveFxAdapter
from app.adapters.isin_map.repo import JsonIsinMapRepository
from app.adapters.repo_json import JsonNavSnapshotRepository, JsonTransactionRepository
from app.adapters.repo_json.tax_profile_repo import JsonTaxProfileRepository
from app.adapters.thesis_map.repo import JsonThesisMapRepository
from app.adapters.ticker_resolver_factory import build_ticker_resolver
from app.adapters.yfinance_ohlc import YfinanceOhlcAdapter
from app.adapters.yfinance_price import YfinancePriceAdapter
from app.config import get_settings
from app.ports.catalysts import CatalystsRepository
from app.ports.company_data import CompanyDataProvider
from app.ports.fx_feed import HistoricalFxProvider, LiveFxProvider
from app.ports.isin_map import IsinMapRepository
from app.ports.market_data import OhlcDataProvider
from app.ports.nav_repository import NavSnapshotRepository
from app.ports.price_feed import PriceProvider
from app.ports.repository import TransactionRepository
from app.ports.tax_profile_repo import TaxProfileRepository
from app.ports.thesis_map import ThesisMapRepository
from app.ports.ticker_resolver import TickerResolver


@st.cache_resource
def get_nav_snapshot_repo() -> NavSnapshotRepository:
    settings = get_settings()
    return JsonNavSnapshotRepository(settings.nav_snapshots_json_path)


@st.cache_resource
def get_repository() -> TransactionRepository:
    settings = get_settings()
    return JsonTransactionRepository(
        Path(settings.portfolio_json_path),
        nav_repo=get_nav_snapshot_repo(),
    )


@st.cache_resource
def get_tax_profile_repo() -> TaxProfileRepository:
    settings = get_settings()
    return JsonTaxProfileRepository(Path(settings.tax_profile_json_path))


@st.cache_resource
def get_price_provider() -> PriceProvider:
    return YfinancePriceAdapter()


@st.cache_resource
def get_historical_fx_provider() -> HistoricalFxProvider:
    settings = get_settings()
    return EcbFxAdapter(cache_path=settings.fx_cache_dir / "ecb.json")


@st.cache_resource
def get_live_fx_provider() -> LiveFxProvider:
    return YfinanceLiveFxAdapter()


@st.cache_resource
def get_ticker_resolver() -> TickerResolver:
    settings = get_settings()
    return build_ticker_resolver(
        cache_path=settings.ticker_cache_json_path,
        finnhub_api_key=settings.finnhub_api_key,
    )


@st.cache_resource
def get_ohlc_data_provider() -> OhlcDataProvider:
    return YfinanceOhlcAdapter()


@st.cache_resource
def get_isin_map_repo() -> IsinMapRepository:
    settings = get_settings()
    return JsonIsinMapRepository(settings.isin_map_json_path)


@st.cache_resource
def get_thesis_repo() -> ThesisMapRepository:
    settings = get_settings()
    return JsonThesisMapRepository(settings.thesis_json_path)


@st.cache_resource
def get_catalysts_repo() -> CatalystsRepository:
    settings = get_settings()
    return JsonCatalystsRepository(settings.catalysts_json_path)


@st.cache_resource
def get_company_provider() -> CompanyDataProvider:
    return build_company_provider()
