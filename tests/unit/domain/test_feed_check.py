from decimal import Decimal

from app.domain.feed_check import evaluate_deviations


def test_three_close_pairs_are_ok_and_use_median() -> None:
    result = evaluate_deviations(
        "US0000000001",
        "GOOD",
        [
            (Decimal("100"), Decimal("100")),
            (Decimal("101"), Decimal("100")),
            (Decimal("102"), Decimal("100")),
        ],
    )

    assert result.status == "ok"
    assert result.compared == 3
    assert result.median_deviation_pct == Decimal("1")
    assert result.avg_trade_price_eur == Decimal("101")
    assert result.avg_close_eur == Decimal("100")
    assert "GOOD closed at €100.00" in result.detail


def test_ten_times_price_is_suspicious() -> None:
    result = evaluate_deviations(
        "US0000000002", "WRONG", [(Decimal("200"), Decimal("20"))]
    )

    assert result.status == "suspicious"
    assert result.median_deviation_pct == Decimal("900")


def test_empty_pairs_with_ticker_are_no_feed() -> None:
    result = evaluate_deviations("US0000000003", "MISSING", [])

    assert result.status == "no_feed"
    assert result.compared == 0
    assert result.median_deviation_pct is None
    assert result.avg_trade_price_eur is None
    assert result.avg_close_eur is None


def test_no_ticker_is_unchecked_even_if_pairs_are_supplied() -> None:
    result = evaluate_deviations(
        "US0000000004", None, [(Decimal("100"), Decimal("100"))]
    )

    assert result.status == "unchecked"
    assert result.compared == 0
    assert result.median_deviation_pct is None


def test_two_pairs_use_arithmetic_mean_deviation() -> None:
    result = evaluate_deviations(
        "US0000000005",
        "MIXED",
        [(Decimal("100"), Decimal("100")), (Decimal("140"), Decimal("100"))],
    )

    assert result.status == "suspicious"
    assert result.median_deviation_pct == Decimal("20")


def test_one_pair_uses_its_deviation() -> None:
    result = evaluate_deviations(
        "US0000000006", "ONE", [(Decimal("110"), Decimal("100"))]
    )

    assert result.status == "ok"
    assert result.compared == 1
    assert result.median_deviation_pct == Decimal("10")
