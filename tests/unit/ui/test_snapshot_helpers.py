from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.company import PriceHistoryPoint, QuarterlyFundamentals
from app.ui.pages._snapshot_helpers import (
    compute_ebit_margin,
    compute_fcf_yield,
    compute_historical_pe_range,
    compute_net_debt_ebitda,
    compute_revenue_cagr,
    compute_sma,
    filter_price_history,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quarter(
    period_end: date,
    revenue: Decimal | None = None,
    operating_income: Decimal | None = None,
    net_debt: Decimal | None = None,
    ebitda: Decimal | None = None,
    free_cash_flow: Decimal | None = None,
    eps_diluted: Decimal | None = None,
) -> QuarterlyFundamentals:
    return QuarterlyFundamentals(
        period_end=period_end,
        revenue=revenue,
        gross_profit=None,
        operating_income=operating_income,
        net_income=None,
        free_cash_flow=free_cash_flow,
        eps_diluted=eps_diluted,
        shares_diluted=None,
        total_debt=None,
        cash_and_equivalents=None,
        net_debt=net_debt,
        ebitda=ebitda,
        currency="USD",
    )


def _price_point(d: date, close: Decimal) -> PriceHistoryPoint:
    return PriceHistoryPoint(date=d, close=close, volume=None)


# ---------------------------------------------------------------------------
# filter_price_history
# ---------------------------------------------------------------------------


def test_filter_price_history_1y():
    history = [
        _price_point(date(2020, 1, 1), Decimal("100")),
        _price_point(date(2023, 6, 1), Decimal("200")),
        _price_point(date(2025, 1, 1), Decimal("300")),
    ]
    result = filter_price_history(history, years=1)
    assert all(p.date >= date(2024, 1, 1) for p in result)
    assert len(result) == 1
    assert result[0].close == Decimal("300")


def test_filter_price_history_empty():
    assert filter_price_history([], years=5) == []


# ---------------------------------------------------------------------------
# compute_sma
# ---------------------------------------------------------------------------


def test_sma_correct_values():
    closes = [Decimal(str(i)) for i in range(1, 6)]  # [1, 2, 3, 4, 5]
    result = compute_sma(closes, 3)
    assert result[0] is None
    assert result[1] is None
    assert result[2] == Decimal("2")
    assert result[3] == Decimal("3")
    assert result[4] == Decimal("4")


def test_sma_period_longer_than_data():
    closes = [Decimal("10"), Decimal("20")]
    result = compute_sma(closes, 5)
    assert all(v is None for v in result)


def test_sma_length_matches_input():
    closes = [Decimal(str(i)) for i in range(250)]
    result = compute_sma(closes, 200)
    assert len(result) == 250
    assert result[198] is None
    assert result[199] is not None


# ---------------------------------------------------------------------------
# compute_revenue_cagr
# ---------------------------------------------------------------------------


def test_revenue_cagr_3y():
    quarters = [
        _make_quarter(date(2022, 3, 31), revenue=Decimal("100")),
        *[_make_quarter(date(2022, 6, 30))] * 11,
        _make_quarter(date(2025, 3, 31), revenue=Decimal("100") * Decimal("1.1") ** 3),
    ]
    cagr, label = compute_revenue_cagr(quarters)
    assert cagr is not None
    assert abs(cagr - Decimal("0.1")) < Decimal("0.005")
    assert "3Y" in label


def test_revenue_cagr_2y():
    quarters = [
        _make_quarter(date(2023, 1, 1), revenue=Decimal("100")),
        *[_make_quarter(date(2023, 4, 1))] * 7,
        _make_quarter(date(2025, 1, 1), revenue=Decimal("121")),
    ]
    cagr, label = compute_revenue_cagr(quarters)
    assert cagr is not None
    assert "2Y" in label


def test_revenue_cagr_insufficient_data():
    quarters = [_make_quarter(date(2025, 1, 1), revenue=Decimal("100"))]
    cagr, label = compute_revenue_cagr(quarters)
    assert cagr is None
    assert label == ""


def test_revenue_cagr_no_revenue():
    quarters = [
        _make_quarter(date(2023, 1, 1)),
        _make_quarter(date(2024, 1, 1)),
    ]
    cagr, label = compute_revenue_cagr(quarters)
    assert cagr is None


# ---------------------------------------------------------------------------
# compute_ebit_margin
# ---------------------------------------------------------------------------


def test_ebit_margin_correct():
    quarters = [
        _make_quarter(date(2025, 3, 31), operating_income=Decimal("18"), revenue=Decimal("100"))
    ]
    result = compute_ebit_margin(quarters)
    assert result == Decimal("0.18")


def test_ebit_margin_none_revenue():
    quarters = [_make_quarter(date(2025, 3, 31), operating_income=Decimal("18"), revenue=None)]
    assert compute_ebit_margin(quarters) is None


def test_ebit_margin_zero_revenue():
    quarters = [
        _make_quarter(date(2025, 3, 31), operating_income=Decimal("18"), revenue=Decimal("0"))
    ]
    assert compute_ebit_margin(quarters) is None


def test_ebit_margin_empty():
    assert compute_ebit_margin([]) is None


# ---------------------------------------------------------------------------
# compute_net_debt_ebitda
# ---------------------------------------------------------------------------


def test_net_debt_ebitda_four_quarters():
    quarters = [
        _make_quarter(date(2024, 3, 31), net_debt=Decimal("80"), ebitda=Decimal("10")),
        _make_quarter(date(2024, 6, 30), net_debt=Decimal("80"), ebitda=Decimal("10")),
        _make_quarter(date(2024, 9, 30), net_debt=Decimal("80"), ebitda=Decimal("10")),
        _make_quarter(date(2024, 12, 31), net_debt=Decimal("80"), ebitda=Decimal("10")),
    ]
    result = compute_net_debt_ebitda(quarters)
    assert result is not None
    assert result == Decimal("2.0")


def test_net_debt_ebitda_fewer_than_4_quarters_annualizes():
    quarters = [
        _make_quarter(date(2024, 3, 31), net_debt=Decimal("80"), ebitda=Decimal("10")),
    ]
    result = compute_net_debt_ebitda(quarters)
    assert result is not None
    assert result == Decimal("2.0")


def test_net_debt_ebitda_negative_ebitda_returns_none():
    quarters = [
        _make_quarter(date(2024, 3, 31), net_debt=Decimal("80"), ebitda=Decimal("-5")),
    ]
    assert compute_net_debt_ebitda(quarters) is None


def test_net_debt_ebitda_no_data():
    assert compute_net_debt_ebitda([]) is None


# ---------------------------------------------------------------------------
# compute_fcf_yield
# ---------------------------------------------------------------------------


def test_fcf_yield_correct():
    quarters = [
        _make_quarter(date(2024, 3, 31), free_cash_flow=Decimal("2.5e9")),
        _make_quarter(date(2024, 6, 30), free_cash_flow=Decimal("2.5e9")),
        _make_quarter(date(2024, 9, 30), free_cash_flow=Decimal("2.5e9")),
        _make_quarter(date(2024, 12, 31), free_cash_flow=Decimal("2.5e9")),
    ]
    result = compute_fcf_yield(quarters, market_cap_amount=Decimal("200e9"))
    assert result is not None
    assert abs(result - Decimal("0.05")) < Decimal("0.0001")


def test_fcf_yield_no_fcf_data():
    quarters = [_make_quarter(date(2024, 3, 31))]
    assert compute_fcf_yield(quarters, market_cap_amount=Decimal("200e9")) is None


def test_fcf_yield_no_market_cap():
    quarters = [_make_quarter(date(2024, 3, 31), free_cash_flow=Decimal("10e9"))]
    assert compute_fcf_yield(quarters, market_cap_amount=None) is None


# ---------------------------------------------------------------------------
# compute_historical_pe_range
# ---------------------------------------------------------------------------


def test_historical_pe_range_correct():
    # 8 quarters with EPS=1 per quarter (TTM=4); prices at quarter end = 80 => P/E=20
    quarters = []
    prices = []
    for i in range(8):
        d = date(2023 + i // 4, (i % 4) * 3 + 1, 28)
        quarters.append(_make_quarter(d, eps_diluted=Decimal("1")))
        prices.append(_price_point(d, Decimal("80")))

    result = compute_historical_pe_range(quarters, prices)
    assert result is not None
    min_pe, current_pe, max_pe = result
    assert abs(current_pe - Decimal("20")) < Decimal("0.5")
    assert min_pe <= current_pe <= max_pe


def test_historical_pe_range_insufficient_quarters():
    quarters = [_make_quarter(date(2025, 1, 1), eps_diluted=Decimal("1"))]
    prices = [_price_point(date(2025, 1, 1), Decimal("20"))]
    assert compute_historical_pe_range(quarters, prices) is None


def test_historical_pe_range_no_price_history():
    quarters = [_make_quarter(date(2025, i, 1), eps_diluted=Decimal("1")) for i in range(1, 5)]
    assert compute_historical_pe_range(quarters, []) is None


def test_historical_pe_range_negative_eps_skipped():
    quarters = [
        _make_quarter(date(2024, 1, 1), eps_diluted=Decimal("-1")),
        _make_quarter(date(2024, 4, 1), eps_diluted=Decimal("-1")),
        _make_quarter(date(2024, 7, 1), eps_diluted=Decimal("-1")),
        _make_quarter(date(2024, 10, 1), eps_diluted=Decimal("-1")),
    ]
    prices = [_price_point(date(2024, 10, 1), Decimal("50"))]
    assert compute_historical_pe_range(quarters, prices) is None
