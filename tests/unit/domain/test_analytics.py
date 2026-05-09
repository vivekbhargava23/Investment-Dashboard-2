"""Unit tests for app.domain.analytics — one class per function."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.analytics import (
    correlation_matrix,
    daily_returns,
    drawdown_series,
    max_drawdown,
    rsi,
    sharpe,
    sma,
    volatility_annualised,
)

# ── TestDailyReturns ───────────────────────────────────────────────────────────


class TestDailyReturns:
    def test_happy_path(self) -> None:
        result = daily_returns([Decimal("100"), Decimal("110"), Decimal("99")])
        # (110-100)/100 = 0.1; (99-110)/110 = -11/110 = -0.1
        assert len(result) == 2
        assert result[0] == Decimal("0.1")
        assert result[1].quantize(Decimal("0.0001")) == Decimal("-0.1000")

    def test_returns_fractions_not_percentages(self) -> None:
        result = daily_returns([Decimal("100"), Decimal("105")])
        assert result == [Decimal("0.05")]

    def test_empty_input(self) -> None:
        assert daily_returns([]) == []

    def test_single_value(self) -> None:
        assert daily_returns([Decimal("50")]) == []

    def test_n_closes_yields_n_minus_one_returns(self) -> None:
        closes = [Decimal(str(i)) for i in range(1, 11)]
        assert len(daily_returns(closes)) == 9


# ── TestVolatilityAnnualised ───────────────────────────────────────────────────


class TestVolatilityAnnualised:
    def test_happy_path(self) -> None:
        # Two-element list: stdev of [0.1, -0.1] = sqrt(0.02) ≈ 0.1414
        # Annualised: 0.1414 × sqrt(252) ≈ 2.245
        returns = [Decimal("0.1"), Decimal("-0.1")]
        result = volatility_annualised(returns)
        assert result > 0
        # Rough sanity: sample stdev of [0.1, -0.1] = sqrt(0.02), annualised × sqrt(252)
        import math
        expected = Decimal(str(math.sqrt(0.02) * math.sqrt(252)))
        assert abs(result - expected) < Decimal("0.001")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 2 returns required"):
            volatility_annualised([])

    def test_single_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 2 returns required"):
            volatility_annualised([Decimal("0.05")])

    def test_result_is_positive(self) -> None:
        result = volatility_annualised([Decimal("0.01"), Decimal("0.02"), Decimal("-0.01")])
        assert result > 0


# ── TestDrawdownSeries ─────────────────────────────────────────────────────────


class TestDrawdownSeries:
    def test_happy_path(self) -> None:
        # 100 → 120 → 90: peak stays at 120 for last, drawdown = (90-120)/120 = -0.25
        navs = [Decimal("100"), Decimal("120"), Decimal("90")]
        result = drawdown_series(navs)
        assert len(result) == 3
        assert result[0] == Decimal("0")  # peak = nav = 100
        assert result[1] == Decimal("0")  # peak = nav = 120
        assert result[2] == Decimal("-0.25")

    def test_empty(self) -> None:
        assert drawdown_series([]) == []

    def test_single_value(self) -> None:
        assert drawdown_series([Decimal("50")]) == [Decimal("0")]

    def test_monotonically_rising_series_all_zero(self) -> None:
        navs = [Decimal(str(i)) for i in range(1, 6)]
        for dd in drawdown_series(navs):
            assert dd == Decimal("0")

    @given(
        st.lists(
            st.decimals(
                min_value=Decimal("0.01"), max_value=Decimal("1000"),
                allow_nan=False, allow_infinity=False,
            ),
            min_size=1,
            max_size=50,
        )
    )
    @settings(max_examples=200)
    def test_all_values_nonpositive(self, navs: list[Decimal]) -> None:
        for dd in drawdown_series(navs):
            assert dd <= Decimal("0")


# ── TestMaxDrawdown ────────────────────────────────────────────────────────────


class TestMaxDrawdown:
    def test_happy_path(self) -> None:
        navs = [Decimal("100"), Decimal("120"), Decimal("90")]
        assert max_drawdown(navs) == Decimal("-0.25")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            max_drawdown([])

    def test_single_value(self) -> None:
        assert max_drawdown([Decimal("100")]) == Decimal("0")

    def test_result_nonpositive(self) -> None:
        navs = [Decimal("50"), Decimal("40"), Decimal("60"), Decimal("30")]
        assert max_drawdown(navs) <= Decimal("0")


# ── TestSharpe ────────────────────────────────────────────────────────────────


class TestSharpe:
    def test_happy_path_positive_sharpe(self) -> None:
        # Positive mean return with non-zero variance → positive Sharpe
        returns = [Decimal("0.01")] * 5 + [Decimal("0.02")]
        result = sharpe(returns)
        assert result > 0

    def test_negative_mean_returns_negative_sharpe(self) -> None:
        returns = [Decimal("-0.02"), Decimal("-0.01"), Decimal("-0.015"), Decimal("-0.025")]
        result = sharpe(returns)
        assert result < 0

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 2 returns required"):
            sharpe([])

    def test_single_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 2 returns required"):
            sharpe([Decimal("0.01")])

    def test_zero_variance_raises(self) -> None:
        with pytest.raises(ValueError, match="zero variance"):
            sharpe([Decimal("0.01"), Decimal("0.01"), Decimal("0.01")])

    def test_risk_free_lowers_sharpe(self) -> None:
        returns = [Decimal("0.01"), Decimal("0.02"), Decimal("0.015"), Decimal("0.01")]
        base = sharpe(returns)
        adjusted = sharpe(returns, risk_free=Decimal("0.005"))
        assert adjusted < base


# ── TestSma ───────────────────────────────────────────────────────────────────


class TestSma:
    def test_happy_path_period_3(self) -> None:
        closes = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
        result = sma(closes, 3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] == Decimal("2")
        assert result[3] == Decimal("3")
        assert result[4] == Decimal("4")

    def test_empty(self) -> None:
        assert sma([], 3) == []

    def test_period_one_returns_same_values(self) -> None:
        closes = [Decimal("5"), Decimal("10"), Decimal("15")]
        result = sma(closes, 1)
        assert result == closes

    def test_period_greater_than_length_all_none(self) -> None:
        closes = [Decimal("1"), Decimal("2")]
        result = sma(closes, 5)
        assert all(v is None for v in result)

    def test_period_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            sma([Decimal("1")], 0)

    def test_period_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            sma([Decimal("1")], -1)

    def test_first_period_minus_one_entries_are_none(self) -> None:
        closes = [Decimal(str(i)) for i in range(1, 11)]
        result = sma(closes, 4)
        assert result[0] is None
        assert result[1] is None
        assert result[2] is None
        assert result[3] is not None


# ── TestRsi ───────────────────────────────────────────────────────────────────


class TestRsi:
    def test_empty_short_series_returns_empty(self) -> None:
        assert rsi([], 14) == []
        assert rsi([Decimal("1")] * 5, 14) == []

    def test_exactly_period_plus_one_returns_one_non_none(self) -> None:
        closes = [Decimal(str(i)) for i in range(1, 16)]  # 15 closes, period=14
        result = rsi(closes, 14)
        assert len(result) == 15
        assert all(v is None for v in result[:14])
        assert result[14] is not None

    def test_first_period_entries_are_none(self) -> None:
        closes = [Decimal(str(100 + i)) for i in range(30)]
        result = rsi(closes, 14)
        assert len(result) == 30
        assert all(v is None for v in result[:14])

    def test_pure_uptrend_rsi_at_or_near_100(self) -> None:
        # All closes strictly increasing → no losses → RSI = 100
        closes = [Decimal(str(100 + i)) for i in range(20)]
        result = rsi(closes, 14)
        non_none = [v for v in result if v is not None]
        for val in non_none:
            assert val == Decimal(100)

    def test_output_length_equals_input_length(self) -> None:
        closes = [Decimal(str(i % 10 + 1)) for i in range(50)]
        result = rsi(closes, 14)
        assert len(result) == 50

    @given(
        st.lists(
            st.decimals(
                min_value=Decimal("1"), max_value=Decimal("1000"),
                allow_nan=False, allow_infinity=False,
            ),
            min_size=30,
            max_size=100,
        )
    )
    @settings(max_examples=100)
    def test_rsi_range_invariant(self, closes: list[Decimal]) -> None:
        result = rsi(closes, 14)
        for val in result:
            if val is not None:
                assert Decimal(0) <= val <= Decimal(100)


# ── TestCorrelationMatrix ─────────────────────────────────────────────────────


class TestCorrelationMatrix:
    def test_empty_input(self) -> None:
        assert correlation_matrix({}) == {}

    def test_single_ticker(self) -> None:
        result = correlation_matrix({"AAPL": [Decimal("0.01"), Decimal("-0.01"), Decimal("0.02")]})
        assert result == {"AAPL": {"AAPL": Decimal(1)}}

    def test_diagonal_is_one(self) -> None:
        data = {
            "A": [Decimal("0.01"), Decimal("0.02"), Decimal("-0.01")],
            "B": [Decimal("0.02"), Decimal("-0.01"), Decimal("0.03")],
        }
        result = correlation_matrix(data)
        assert result["A"]["A"] == Decimal(1)
        assert result["B"]["B"] == Decimal(1)

    def test_symmetry(self) -> None:
        data = {
            "A": [Decimal("0.01"), Decimal("0.02"), Decimal("-0.01"), Decimal("0.03")],
            "B": [Decimal("0.02"), Decimal("-0.01"), Decimal("0.03"), Decimal("0.01")],
            "C": [Decimal("-0.01"), Decimal("0.03"), Decimal("0.01"), Decimal("0.02")],
        }
        result = correlation_matrix(data)
        tickers = list(data.keys())
        for a in tickers:
            for b in tickers:
                assert result[a][b] == result[b][a], f"Asymmetry: {a}↔{b}"

    def test_perfect_positive_correlation(self) -> None:
        series = [Decimal("0.01"), Decimal("0.02"), Decimal("0.03")]
        data = {"A": series, "B": series}
        result = correlation_matrix(data)
        assert abs(result["A"]["B"] - Decimal(1)) < Decimal("0.0001")

    def test_perfect_negative_correlation(self) -> None:
        a = [Decimal("0.01"), Decimal("0.02"), Decimal("0.03")]
        b = [Decimal("-0.01"), Decimal("-0.02"), Decimal("-0.03")]
        result = correlation_matrix({"A": a, "B": b})
        assert abs(result["A"]["B"] - Decimal(-1)) < Decimal("0.0001")

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError, match="series length mismatch"):
            correlation_matrix({"A": [Decimal(1), Decimal(2)], "B": [Decimal(3)]})

    def test_mismatched_length_error_names_tickers(self) -> None:
        with pytest.raises(ValueError, match="A has 2"):
            correlation_matrix({"A": [Decimal(1), Decimal(2)], "B": [Decimal(3)]})

    def test_three_ticker_symmetry(self) -> None:
        import random
        random.seed(42)
        tickers = ["X", "Y", "Z"]
        data = {t: [Decimal(str(random.gauss(0, 0.01))) for _ in range(100)] for t in tickers}
        result = correlation_matrix(data)
        for a in data:
            assert result[a][a] == Decimal(1)
            for b in data:
                assert result[a][b] == result[b][a]
