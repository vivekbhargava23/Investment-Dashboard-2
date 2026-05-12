from __future__ import annotations

import logging
import os
from pathlib import Path

from app.adapters.company_cache.adapter import CacheCompanyAdapter
from app.adapters.company_composite.adapter import CompositeCompanyAdapter
from app.adapters.company_yfinance.adapter import YfinanceCompanyAdapter
from app.ports.company_data import CompanyDataProvider

_log = logging.getLogger(__name__)


def build_company_provider(
    cache_root: Path = Path("data/companies"),
    finnhub_api_key: str | None = None,
) -> CompanyDataProvider:
    """Build the production CompanyDataProvider: cache(composite(yfinance, [finnhub]))."""
    if finnhub_api_key is None:
        finnhub_api_key = os.environ.get("FINNHUB_API_KEY") or ""

    yfinance_adapter = YfinanceCompanyAdapter()

    if finnhub_api_key:
        from app.adapters.company_finnhub.adapter import FinnhubCompanyAdapter

        finnhub_adapter = FinnhubCompanyAdapter(api_key=finnhub_api_key)
        composite: CompanyDataProvider = CompositeCompanyAdapter(yfinance_adapter, finnhub_adapter)
    else:
        _log.info("FINNHUB_API_KEY not set; building company provider with yfinance only")
        composite = CompositeCompanyAdapter(yfinance_adapter)

    return CacheCompanyAdapter(inner=composite, cache_root=cache_root)
