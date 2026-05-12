from __future__ import annotations

import pytest

from app.adapters.company_yfinance.adapter import YfinanceCompanyAdapter
from app.ports.company_data import CompanyDataError


@pytest.mark.integration
def test_get_company_nvda_returns_basic_data() -> None:
    adapter = YfinanceCompanyAdapter()
    data = adapter.get_company("NVDA")

    assert data.profile is not None
    assert data.latest_quote is not None
    assert len(data.price_history) > 0


@pytest.mark.integration
def test_invalid_ticker_raises_company_data_error() -> None:
    adapter = YfinanceCompanyAdapter()
    with pytest.raises(CompanyDataError):
        adapter.get_company("NOTAREALTICKERZZZZ")
