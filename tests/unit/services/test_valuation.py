from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.services.valuation import (
    clear_caches,
    clear_live_positions_cache,
    compute_live_positions,
    compute_portfolio_summary,
    get_live_positions_cached,
)
from tests.fakes.fx_feed import FakeFxProvider
from tests.fakes.price_feed import FakePriceProvider


class _FakeRepo:
    def __init__(self, transactions: list[Transaction]) -> None:
        self._transactions = transactions

    def load_all(self) -> list[Transaction]:
        return list(self._transactions)

    def save_all(self, txs: object) -> None:  # type: ignore[override]
        pass

    def add(self, tx: Transaction) -> None:
        self._transactions.append(tx)

    def update(self, tx: Transaction) -> None:
        pass

    def delete(self, tx_id: str) -> None:
        pass

    def get(self, tx_id: str) -> Transaction:
        raise KeyError(tx_id)


@pytest.fixture
def eur_buy() -> Transaction:
    return Transaction(
        id="t1",
        ticker="RHM.DE",
        type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
        fee_native=Money(amount=Decimal("0"), currency=Currency.EUR),
        tax_native=Money(amount=Decimal("0"), currency=Currency.EUR),
    )


@pytest.fixture
def usd_buy() -> Transaction:
    # 10 shares at $100 each. Cost $1000.
    # FX rate 0.9 EUR per 1 USD -> Cost €900.
    return Transaction(
        id="t2",
        ticker="NVDA",
        type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.USD),
        fx_rate_eur=Decimal("0.9"),
        fee_native=Money(amount=Decimal("0"), currency=Currency.USD),
        tax_native=Money(amount=Decimal("0"), currency=Currency.USD),
    )


@pytest.fixture
def jpy_buy() -> Transaction:
    # 10 shares at ¥1000 each. Cost ¥10,000.
    # fx_rate_eur 0.005 EUR per 1 JPY -> cost €50.
    return Transaction(
        id="t3",
        ticker="7203.T",
        type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("1000"), currency=Currency.JPY),
        fx_rate_eur=Decimal("0.005"),
        fee_native=Money(amount=Decimal("0"), currency=Currency.JPY),
        tax_native=Money(amount=Decimal("0"), currency=Currency.JPY),
    )


def test_compute_live_positions_eur_happy_path(eur_buy: Transaction) -> None:
    pp = FakePriceProvider(
        current_prices={"RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR)}
    )
    fp = FakeFxProvider()

    res = compute_live_positions([eur_buy], pp, fp, date(2026, 6, 7))

    assert "RHM.DE" in res
    lp = res["RHM.DE"]
    assert lp.ticker == "RHM.DE"
    assert lp.live_price_native == Money(amount=Decimal("110"), currency=Currency.EUR)
    assert lp.live_value_eur == Money(amount=Decimal("1100"), currency=Currency.EUR)
    assert lp.unrealised_gain_eur == Money(amount=Decimal("100"), currency=Currency.EUR)
    assert lp.unrealised_gain_pct == Decimal("10")
    assert not lp.is_stale


def test_compute_live_positions_usd_happy_path(usd_buy: Transaction) -> None:
    # Current price $110.
    # Current FX: 1.1 USD per 1 EUR -> 1 USD = 1/1.1 EUR = 0.909091 EUR.
    # Value in EUR = 10 * 110 * (1/1.1) = 1100 / 1.1 = 1000 EUR.
    # Cost basis was €900.
    # Gain = €100.
    pp = FakePriceProvider(
        current_prices={"NVDA": Money(amount=Decimal("110"), currency=Currency.USD)}
    )
    fp = FakeFxProvider(current_rates={(Currency.EUR, Currency.USD): Decimal("1.1")})

    res = compute_live_positions([usd_buy], pp, fp, date(2026, 6, 7))

    assert "NVDA" in res
    lp = res["NVDA"]
    assert lp.live_value_eur == Money(amount=Decimal("1000"), currency=Currency.EUR)
    assert lp.unrealised_gain_eur == Money(amount=Decimal("100"), currency=Currency.EUR)
    assert not lp.is_stale


def test_compute_live_positions_mixed_all_live(eur_buy: Transaction, usd_buy: Transaction) -> None:
    pp = FakePriceProvider(
        current_prices={
            "RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR),
            "NVDA": Money(amount=Decimal("110"), currency=Currency.USD),
        }
    )
    fp = FakeFxProvider(current_rates={(Currency.EUR, Currency.USD): Decimal("1.1")})

    res = compute_live_positions([eur_buy, usd_buy], pp, fp, date(2026, 6, 7))
    assert len(res) == 2
    assert all(not lp.is_stale for lp in res.values())


def test_compute_live_positions_empty() -> None:
    pp = FakePriceProvider()
    fp = FakeFxProvider()
    res = compute_live_positions([], pp, fp, date(2026, 6, 7))
    assert res == {}


def test_per_ticker_failure_isolation(eur_buy: Transaction) -> None:
    # Two transactions, one price missing from the fake provider
    t2 = Transaction(
        id="t2",
        ticker="NOPRICE.DE",
        type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        shares=Decimal("10"),
        price_native=Money(amount=Decimal("100"), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )

    pp = FakePriceProvider(
        current_prices={"RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR)}
        # "NOPRICE.DE" is intentionally absent
    )
    fp = FakeFxProvider()

    res = compute_live_positions([eur_buy, t2], pp, fp, date(2026, 6, 7))

    assert res["RHM.DE"].is_stale is False
    assert res["NOPRICE.DE"].is_stale is True
    assert res["NOPRICE.DE"].staleness_reason == "Live price unavailable"


def test_fx_failure_marks_usd_stale(eur_buy: Transaction, usd_buy: Transaction) -> None:
    pp = FakePriceProvider(
        current_prices={
            "RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR),
            "NVDA": Money(amount=Decimal("110"), currency=Currency.USD),
        }
    )
    fp = FakeFxProvider()  # Missing FX rate

    res = compute_live_positions([eur_buy, usd_buy], pp, fp, date(2026, 6, 7))

    assert res["RHM.DE"].is_stale is False
    assert res["NVDA"].is_stale is True
    assert res["NVDA"].staleness_reason == "FX rate USD/EUR unavailable"


def test_compute_live_positions_jpy_happy_path(jpy_buy: Transaction) -> None:
    # Current price ¥1200, FX rate 160 JPY per 1 EUR.
    # Value in EUR = 10 * 1200 / 160 = €75. Cost basis was €50. Gain = €25.
    pp = FakePriceProvider(
        current_prices={"7203.T": Money(amount=Decimal("1200"), currency=Currency.JPY)}
    )
    fp = FakeFxProvider(current_rates={(Currency.EUR, Currency.JPY): Decimal("160")})

    res = compute_live_positions([jpy_buy], pp, fp, date(2026, 6, 7))

    lp = res["7203.T"]
    assert not lp.is_stale
    assert lp.live_value_eur == Money(amount=Decimal("75"), currency=Currency.EUR)
    assert lp.unrealised_gain_eur == Money(amount=Decimal("25"), currency=Currency.EUR)


def test_compute_live_positions_jpy_stale_without_rate(jpy_buy: Transaction) -> None:
    # JPY price fetched fine, but no JPY FX rate -> stale (not silently mis-valued).
    pp = FakePriceProvider(
        current_prices={"7203.T": Money(amount=Decimal("1200"), currency=Currency.JPY)}
    )
    fp = FakeFxProvider()  # no rates configured

    res = compute_live_positions([jpy_buy], pp, fp, date(2026, 6, 7))

    lp = res["7203.T"]
    assert lp.is_stale is True
    assert lp.staleness_reason == "FX rate JPY/EUR unavailable"


def test_fx_fetched_once_per_distinct_currency(
    usd_buy: Transaction, jpy_buy: Transaction
) -> None:
    # Two USD positions + one JPY position -> exactly two FX lookups (USD, JPY),
    # not one per position.
    usd_buy_2 = usd_buy.model_copy(update={"id": "t2b", "ticker": "MU"})
    pp = FakePriceProvider(
        current_prices={
            "NVDA": Money(amount=Decimal("110"), currency=Currency.USD),
            "MU": Money(amount=Decimal("90"), currency=Currency.USD),
            "7203.T": Money(amount=Decimal("1200"), currency=Currency.JPY),
        }
    )
    fp = FakeFxProvider(
        current_rates={
            (Currency.EUR, Currency.USD): Decimal("1.1"),
            (Currency.EUR, Currency.JPY): Decimal("160"),
        }
    )
    original = fp.get_current_rate
    fp.get_current_rate = MagicMock(side_effect=original)  # type: ignore

    compute_live_positions([usd_buy, usd_buy_2, jpy_buy], pp, fp, date(2026, 6, 7))

    assert fp.get_current_rate.call_count == 2
    requested = {call.args[1] for call in fp.get_current_rate.call_args_list}
    assert requested == {Currency.USD, Currency.JPY}


def test_compute_live_positions_one_batched_price_fetch(
    eur_buy: Transaction, usd_buy: Transaction
) -> None:
    # A portfolio of N positions triggers exactly one batched price fetch.
    pp = FakePriceProvider(
        current_prices={
            "RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR),
            "NVDA": Money(amount=Decimal("110"), currency=Currency.USD),
        }
    )
    fp = FakeFxProvider(current_rates={(Currency.EUR, Currency.USD): Decimal("1.1")})

    compute_live_positions([eur_buy, usd_buy], pp, fp, date(2026, 6, 7))

    assert pp.batch_call_count == 1


def test_portfolio_summary_aggregates_live_only(eur_buy: Transaction) -> None:
    # 2 live, 1 stale
    t2 = eur_buy.model_copy(update={"id": "t2", "ticker": "LIVE2"})
    t_stale = eur_buy.model_copy(update={"id": "t3", "ticker": "STALE"})

    pp = FakePriceProvider(
        current_prices={
            "RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR),
            "LIVE2": Money(amount=Decimal("110"), currency=Currency.EUR),
        }
    )
    fp = FakeFxProvider()

    res = compute_live_positions([eur_buy, t2, t_stale], pp, fp, date(2026, 6, 7))
    lp1 = res["RHM.DE"]
    lp2 = res["LIVE2"]
    lp_stale = res["STALE"]

    summary = compute_portfolio_summary(res, datetime.now())

    assert summary.position_count == 3
    assert summary.live_position_count == 2
    assert summary.staleness == "partial"
    # Value should only be from lp1 + lp2
    assert summary.total_value_eur.amount == lp1.live_value_eur.amount + lp2.live_value_eur.amount
    # Cost basis should be from all three
    assert summary.total_cost_basis_eur.amount == (
        lp1.position.cost_basis_eur.amount
        + lp2.position.cost_basis_eur.amount
        + lp_stale.position.cost_basis_eur.amount
    )


def test_compute_live_positions_has_no_state(eur_buy: Transaction) -> None:
    # compute_live_positions is stateless; two calls hit the provider twice.
    pp = FakePriceProvider(
        current_prices={"RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR)}
    )
    fp = FakeFxProvider()

    original_method = pp.get_current_prices
    pp.get_current_prices = MagicMock(side_effect=original_method)  # type: ignore

    compute_live_positions([eur_buy], pp, fp, date(2026, 6, 7))
    compute_live_positions([eur_buy], pp, fp, date(2026, 6, 7))

    assert pp.get_current_prices.call_count == 2


@pytest.fixture(autouse=True)
def _clear_live_positions_cache() -> None:
    clear_live_positions_cache()
    yield  # type: ignore[misc]
    clear_live_positions_cache()


def test_get_live_positions_cached_hits_provider_once(eur_buy: Transaction) -> None:
    pp = FakePriceProvider(
        current_prices={"RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR)}
    )
    fp = FakeFxProvider()
    repo = _FakeRepo([eur_buy])

    original_method = pp.get_current_prices
    pp.get_current_prices = MagicMock(side_effect=original_method)  # type: ignore

    r1 = get_live_positions_cached(
        repo=repo, price_provider=pp, fx_provider=fp, as_of=date(2026, 6, 7)
    )
    r2 = get_live_positions_cached(
        repo=repo, price_provider=pp, fx_provider=fp, as_of=date(2026, 6, 7)
    )

    assert pp.get_current_prices.call_count == 1
    assert r1 is r2


def test_get_live_positions_cached_miss_on_tx_change(eur_buy: Transaction) -> None:
    pp = FakePriceProvider(
        current_prices={
            "RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR),
            "LIVE2": Money(amount=Decimal("50"), currency=Currency.EUR),
        }
    )
    fp = FakeFxProvider()
    t2 = eur_buy.model_copy(update={"id": "t2", "ticker": "LIVE2"})
    repo = _FakeRepo([eur_buy])

    original_method = pp.get_current_prices
    pp.get_current_prices = MagicMock(side_effect=original_method)  # type: ignore

    get_live_positions_cached(repo=repo, price_provider=pp, fx_provider=fp, as_of=date(2026, 6, 7))
    assert pp.get_current_prices.call_count == 1

    # Adding a transaction changes the signature → cache miss → one more batch fetch
    repo.add(t2)
    get_live_positions_cached(repo=repo, price_provider=pp, fx_provider=fp, as_of=date(2026, 6, 7))
    assert pp.get_current_prices.call_count == 2  # one batch fetch per compute


def test_get_live_positions_cached_miss_after_ttl(eur_buy: Transaction) -> None:
    pp = FakePriceProvider(
        current_prices={"RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR)}
    )
    fp = FakeFxProvider()
    repo = _FakeRepo([eur_buy])

    original_method = pp.get_current_prices
    pp.get_current_prices = MagicMock(side_effect=original_method)  # type: ignore

    with patch("app.services.valuation.time") as mock_time:
        mock_time.monotonic.return_value = 1000.0
        get_live_positions_cached(
            repo=repo, price_provider=pp, fx_provider=fp, as_of=date(2026, 6, 7), ttl_seconds=60.0
        )
        assert pp.get_current_prices.call_count == 1

        mock_time.monotonic.return_value = 1000.0 + 59.9
        get_live_positions_cached(
            repo=repo, price_provider=pp, fx_provider=fp, as_of=date(2026, 6, 7), ttl_seconds=60.0
        )
        assert pp.get_current_prices.call_count == 1

        mock_time.monotonic.return_value = 1000.0 + 61.0
        get_live_positions_cached(
            repo=repo, price_provider=pp, fx_provider=fp, as_of=date(2026, 6, 7), ttl_seconds=60.0
        )
        assert pp.get_current_prices.call_count == 2


def test_clear_live_positions_cache(eur_buy: Transaction) -> None:
    pp = FakePriceProvider(
        current_prices={"RHM.DE": Money(amount=Decimal("110"), currency=Currency.EUR)}
    )
    fp = FakeFxProvider()
    repo = _FakeRepo([eur_buy])

    original_method = pp.get_current_prices
    pp.get_current_prices = MagicMock(side_effect=original_method)  # type: ignore

    get_live_positions_cached(repo=repo, price_provider=pp, fx_provider=fp, as_of=date(2026, 6, 7))
    assert pp.get_current_prices.call_count == 1

    clear_live_positions_cache()

    get_live_positions_cached(repo=repo, price_provider=pp, fx_provider=fp, as_of=date(2026, 6, 7))
    assert pp.get_current_prices.call_count == 2


def test_clear_caches() -> None:
    pp = MagicMock(spec=FakePriceProvider)
    fp = MagicMock(spec=FakeFxProvider)

    clear_caches(pp, fp)

    pp.clear_cache.assert_called_once()
    fp.clear_cache.assert_called_once()
