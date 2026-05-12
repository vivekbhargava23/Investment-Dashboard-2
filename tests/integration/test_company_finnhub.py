from __future__ import annotations

import os

import pytest

from app.adapters.company_finnhub.adapter import FinnhubCompanyAdapter
from app.ports.company_data import CompanyDataError


@pytest.mark.integration
def test_get_company_aapl_returns_ownership_and_catalyst() -> None:
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        pytest.skip("FINNHUB_API_KEY not set")

    adapter = FinnhubCompanyAdapter(api_key=api_key)
    data = adapter.get_company("AAPL")

    assert data.next_catalyst is not None or data.ownership is not None


@pytest.mark.integration
def test_invalid_api_key_raises_company_data_error() -> None:
    pytest.skip("FINNHUB_API_KEY not set") if not os.environ.get("FINNHUB_API_KEY") else None
    adapter = FinnhubCompanyAdapter(api_key="invalid_key_xxx")
    with pytest.raises(CompanyDataError):
        adapter.get_company("AAPL")
