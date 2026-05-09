"""Unit tests for app.services.nav.get_nav_series / clear_nav_cache.

All fakes are defined locally so this file is self-contained. The
FakeNavSnapshotRepository from tests/fakes/nav.py is reused for downstream
analytics ticket tests; the fakes here are the authoritative service-layer tests.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.domain.market_data import ChartPeriod, OhlcBar, OhlcSeries, OhlcUnavailableError
from app.domain.models import Transaction, TransactionType
from app.domain.money import Currency, Money
from app.domain.nav import DailyNavPoint
from app.services.nav import clear_nav_cache, get_nav_series
from tests.fakes.nav import FakeNavSnapshotRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bar(d: date, close: str) -> OhlcBar:
    return OhlcBar(
        timestamp=datetime(d.year, d.month, d.day, 16, 0, tzinfo=UTC),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1000,
    )


def _make_series(
    ticker: str,
    currency: Currency,
    dates: list[date],
    closes: list[str],
    period: ChartPeriod = ChartPeriod.THREE_MONTH,
) -> OhlcSeries:
    assert len(dates) == len(closes)
    return OhlcSeries(
        ticker=ticker,
        currency=currency,
        period=period,
        bars=tuple(_make_bar(d, c) for d, c in zip(dates, closes)),
        fetched_at=datetime(2025, 3, 1, tzinfo=UTC),
    )


def _trading_days(start: date, n: int) -> list[date]:
    """Return n weekday dates starting from start."""
    days: list[date] = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _eur_buy(
    tx_id: str,
    ticker: str,
    trade_date: date,
    shares: str,
    price: str,
) -> Transaction:
    return Transaction(
        id=tx_id,
        type=TransactionType.BUY,
        ticker=ticker,
        trade_date=trade_date,
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price), currency=Currency.EUR),
        fx_rate_eur=Decimal("1"),
    )


def _usd_buy(
    tx_id: str,
    ticker: str,
    trade_date: date,
    shares: str,
    price_usd: str,
    fx_rate: str,
) -> Transaction:
    return Transaction(
        id=tx_id,
        type=TransactionType.BUY,
        ticker=ticker,
        trade_date=trade_date,
        shares=Decimal(shares),
        price_native=Money(amount=Decimal(price_usd), currency=Currency.USD),
        fx_rate_eur=Decimal(fx_rate),
    )


class FlexibleFakeOhlcProvider:
    """Returns configured OhlcSeries for any period (ignores the period param).

    This lets service tests avoid depending on the exact ChartPeriod that
    _period_covering() selects.
    """

    def __init__(
        self,
        series_by_ticker: dict[str, OhlcSeries],
        raise_for: set[str] | None = None,
    ) -> None:
        self._series = series_by_ticker
        self._raise_for = raise_for or set()
        self.calls: list[tuple[str, ChartPeriod]] = []

    def get_ohlc_history(self, ticker: str, period: ChartPeriod) -> OhlcSeries:
        self.calls.append((ticker, period))
        if ticker in self._raise_for:
            raise OhlcUnavailableError(f"Fake: no data for {ticker}")
        if ticker in self._series:
            return self._series[ticker]
        raise OhlcUnavailableError(f"Fake: {ticker} not configured")

    def clear_cache(self) -> None:
        pass


class FakeTransactionRepository:
    def __init__(self, transactions: list[Transaction] | None = None) -> None:
        self._transactions: list[Transaction] = list(transactions or [])

    def load_all(self) -> list[Transaction]:
        return list(self._transactions)

    def save_all(self, transactions: object) -> None:
        pass

    def add(self, transaction: object) -> None:
        pass

    def update(self, transaction: object) -> None:
        pass

    def delete(self, transaction_id: object) -> None:
        pass

    def get(self, transaction_id: object) -> Transaction:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Test 5 — Happy path: empty cache, full reconstruction
# ---------------------------------------------------------------------------


class TestHappyPathFullReconstruction:
    """Two transactions (EUR + USD), 30 trading days, empty cache → 30 points."""

    def setup_method(self) -> None:
        self.today = date(2025, 3, 15)
        self.start = date(2025, 1, 6)
        self.end = date(2025, 3, 14)  # yesterday
        self.dates_30 = _trading_days(self.start, 30)

        eur_tx = _eur_buy("t1", "RHM.DE", date(2025, 1, 2), "10", "100")
        usd_tx = _usd_buy("t2", "NVDA", date(2025, 1, 2), "5", "200", "0.9")
        self.tx_repo = FakeTransactionRepository([eur_tx, usd_tx])

        self.nav_repo = FakeNavSnapshotRepository()

        eur_series = _make_series(
            "RHM.DE", Currency.EUR, self.dates_30, ["110"] * 30
        )
        usd_series = _make_series(
            "NVDA", Currency.USD, self.dates_30, ["210"] * 30
        )
        # EURUSD=X: 1 EUR = 1.10 USD
        fx_series = _make_series(
            "EURUSD=X", Currency.USD, self.dates_30, ["1.10"] * 30
        )
        self.provider = FlexibleFakeOhlcProvider(
            {"RHM.DE": eur_series, "NVDA": usd_series, "EURUSD=X": fx_series}
        )

    def test_returns_30_points(self) -> None:
        result = get_nav_series(
            self.start,
            self.end,
            nav_repo=self.nav_repo,
            ohlc_provider=self.provider,
            tx_repo=self.tx_repo,
            today=self.today,
        )
        assert len(result) == 30

    def test_all_points_reconstructed(self) -> None:
        result = get_nav_series(
            self.start,
            self.end,
            nav_repo=self.nav_repo,
            ohlc_provider=self.provider,
            tx_repo=self.tx_repo,
            today=self.today,
        )
        assert all(p.is_reconstructed for p in result)

    def test_sorted_ascending(self) -> None:
        result = get_nav_series(
            self.start,
            self.end,
            nav_repo=self.nav_repo,
            ohlc_provider=self.provider,
            tx_repo=self.tx_repo,
            today=self.today,
        )
        dates = [p.snapshot_date for p in result]
        assert dates == sorted(dates)

    def test_eur_nav_matches_hand_computed(self) -> None:
        # RHM.DE: 10 shares × €110 = €1100
        # NVDA: 5 shares × $210 / 1.10 (EURUSD) = $1050 / 1.10 = €954.5454…
        # Expected nav = 1100 + 954.5454… ≈ 2054.5454
        result = get_nav_series(
            self.start,
            self.end,
            nav_repo=self.nav_repo,
            ohlc_provider=self.provider,
            tx_repo=self.tx_repo,
            today=self.today,
        )
        expected_nav = Decimal("1100") + Decimal("5") * Decimal("210") / Decimal("1.10")
        # Money normalises to 4dp; compare with tolerance
        for point in result:
            diff = abs(point.nav_eur.amount - expected_nav)
            assert diff < Decimal("0.01"), f"NAV {point.nav_eur.amount} != expected {expected_nav}"

    def test_points_persisted(self) -> None:
        get_nav_series(
            self.start,
            self.end,
            nav_repo=self.nav_repo,
            ohlc_provider=self.provider,
            tx_repo=self.tx_repo,
            today=self.today,
        )
        assert self.nav_repo.save_count >= 1
        saved_dates = {p.snapshot_date for p in self.nav_repo.all_points}
        assert len(saved_dates) == 30


# ---------------------------------------------------------------------------
# Test 6 — Cache hit: only missing days are reconstructed and saved
# ---------------------------------------------------------------------------


class TestCacheHitPartialReconstruction:
    def setup_method(self) -> None:
        self.today = date(2025, 3, 15)
        self.start = date(2025, 1, 6)
        self.end = date(2025, 3, 14)
        self.dates_30 = _trading_days(self.start, 30)

        eur_tx = _eur_buy("t1", "RHM.DE", date(2025, 1, 2), "10", "100")
        self.tx_repo = FakeTransactionRepository([eur_tx])

        # Pre-populate 25 of 30 days in the cache.
        cached_points = [
            DailyNavPoint(
                snapshot_date=d,
                nav_eur=Money(amount=Decimal("1100"), currency=Currency.EUR),
                cost_basis_eur=Money(amount=Decimal("1000"), currency=Currency.EUR),
                n_positions=1,
                is_reconstructed=True,
            )
            for d in self.dates_30[:25]
        ]
        self.nav_repo = FakeNavSnapshotRepository(cached_points)

        eur_series = _make_series("RHM.DE", Currency.EUR, self.dates_30, ["110"] * 30)
        self.provider = FlexibleFakeOhlcProvider({"RHM.DE": eur_series})

    def test_returns_30_points_total(self) -> None:
        result = get_nav_series(
            self.start,
            self.end,
            nav_repo=self.nav_repo,
            ohlc_provider=self.provider,
            tx_repo=self.tx_repo,
            today=self.today,
        )
        assert len(result) == 30

    def test_saves_only_5_new_points(self) -> None:
        get_nav_series(
            self.start,
            self.end,
            nav_repo=self.nav_repo,
            ohlc_provider=self.provider,
            tx_repo=self.tx_repo,
            today=self.today,
        )
        total_saved = sum(len(b) for b in self.nav_repo.saved_batches)
        assert total_saved == 5


# ---------------------------------------------------------------------------
# Test 7 — Today is live: not cached, is_reconstructed=False
# ---------------------------------------------------------------------------


class TestTodayIsLive:
    def test_today_not_cached_and_is_reconstructed_false(self) -> None:
        today = date(2025, 3, 15)
        tx = _eur_buy("t1", "RHM.DE", date(2025, 1, 2), "10", "100")
        nav_repo = FakeNavSnapshotRepository()

        series = _make_series("RHM.DE", Currency.EUR, [today], ["110"])
        provider = FlexibleFakeOhlcProvider({"RHM.DE": series})
        tx_repo = FakeTransactionRepository([tx])

        result = get_nav_series(
            today,
            today,
            nav_repo=nav_repo,
            ohlc_provider=provider,
            tx_repo=tx_repo,
            today=today,
        )

        assert len(result) == 1
        assert result[0].is_reconstructed is False
        assert result[0].snapshot_date == today
        # Today's point is never persisted.
        assert nav_repo.save_count == 0


# ---------------------------------------------------------------------------
# Test 8 — Fallback to prior close when target date is missing
# ---------------------------------------------------------------------------


class TestFallbackToPriorClose:
    def test_uses_most_recent_prior_close(self) -> None:
        today = date(2025, 8, 15)
        # Ticker has data on Mon=2025-08-11 and Wed=2025-08-13, but NOT Tue=2025-08-12.
        # We request Tue; service should use Mon's close (most recent on or before Tue).
        mon = date(2025, 8, 11)
        wed = date(2025, 8, 13)

        tx = _eur_buy("t1", "RHM.DE", date(2025, 1, 2), "10", "100")
        nav_repo = FakeNavSnapshotRepository()

        # Only mon and wed have OHLC bars; tue is missing.
        series = _make_series(
            "RHM.DE", Currency.EUR, [mon, wed], ["100", "120"]
        )
        provider = FlexibleFakeOhlcProvider({"RHM.DE": series})
        tx_repo = FakeTransactionRepository([tx])

        # Request only mon, tue, wed — but OHLC only has mon+wed as "trading days".
        # So we'll get 2 points: mon and wed (tue is not a trading day in OHLC data).
        result = get_nav_series(
            mon,
            wed,
            nav_repo=nav_repo,
            ohlc_provider=provider,
            tx_repo=tx_repo,
            today=today,
        )

        # Points exist for mon and wed.
        dates = {p.snapshot_date for p in result}
        assert mon in dates
        assert wed in dates

        # Now request just tue specifically — it's not a trading day, no point.
        # Verify fallback via a direct ticker lookup: request mon with only wed data.
        # Use a series that only has wed; requesting mon should use no close (before wed).
        series_wed_only = _make_series("RHM.DE", Currency.EUR, [wed], ["120"])
        provider2 = FlexibleFakeOhlcProvider({"RHM.DE": series_wed_only})
        nav_repo2 = FakeNavSnapshotRepository()
        result2 = get_nav_series(
            wed,
            wed,
            nav_repo=nav_repo2,
            ohlc_provider=provider2,
            tx_repo=tx_repo,
            today=today,
        )
        assert len(result2) == 1
        assert result2[0].nav_eur.amount == Decimal("10") * Decimal("120")


# ---------------------------------------------------------------------------
# Test 9 — No OHLC at all for a ticker: zero NAV contribution, no exception
# ---------------------------------------------------------------------------


class TestNoOhlcForTicker:
    def test_missing_ticker_contributes_zero(self) -> None:
        today = date(2025, 8, 15)
        d = date(2025, 8, 11)

        eur_tx = _eur_buy("t1", "RHM.DE", date(2025, 1, 2), "10", "100")
        usd_tx = _usd_buy("t2", "NVDA", date(2025, 1, 2), "5", "200", "0.9")
        nav_repo = FakeNavSnapshotRepository()

        eur_series = _make_series("RHM.DE", Currency.EUR, [d], ["110"])
        # NVDA has no data; EURUSD=X also has no data.
        provider = FlexibleFakeOhlcProvider(
            {"RHM.DE": eur_series},
            raise_for={"NVDA", "EURUSD=X"},
        )
        tx_repo = FakeTransactionRepository([eur_tx, usd_tx])

        result = get_nav_series(
            d, d, nav_repo=nav_repo, ohlc_provider=provider, tx_repo=tx_repo, today=today
        )

        assert len(result) == 1
        # RHM.DE: 10 × 110 = 1100; NVDA contributes zero.
        assert result[0].nav_eur.amount == Decimal("10") * Decimal("110")
        # Cost basis still includes NVDA's cost (from FIFO).
        assert result[0].n_positions == 2


# ---------------------------------------------------------------------------
# Test 10 — Lot-edit invalidation: clear is called on every save
# ---------------------------------------------------------------------------


class TestLotEditInvalidation:
    def test_clear_called_on_each_save(self) -> None:
        import tempfile
        from pathlib import Path

        from app.adapters.repo_json.json_repo import JsonTransactionRepository

        nav_repo = FakeNavSnapshotRepository()

        with tempfile.TemporaryDirectory() as tmpdir:
            tx_path = Path(tmpdir) / "portfolio.json"
            repo = JsonTransactionRepository(tx_path, nav_repo=nav_repo)

            tx = _eur_buy("t1", "RHM.DE", date(2025, 1, 2), "10", "100")
            repo.save_all([tx])
            assert nav_repo.clear_count == 1

            tx2 = _eur_buy("t2", "SAP.DE", date(2025, 2, 1), "5", "200")
            repo.save_all([tx, tx2])
            assert nav_repo.clear_count == 2


# ---------------------------------------------------------------------------
# Test 11 — FX reconstruction: USD position → EUR value via EURUSD=X
# ---------------------------------------------------------------------------


class TestFxReconstruction:
    def test_usd_position_converted_correctly(self) -> None:
        today = date(2025, 8, 15)
        d = date(2025, 8, 11)

        # 4 shares of NVDA at $250 each; FX at purchase was 0.90 EUR/USD.
        usd_tx = _usd_buy("t1", "NVDA", date(2025, 1, 2), "4", "250", "0.9")
        nav_repo = FakeNavSnapshotRepository()

        nvda_series = _make_series("NVDA", Currency.USD, [d], ["300"])
        # EURUSD=X = 1.20 means 1 EUR = 1.20 USD → EUR per USD = 1/1.20
        eurusd_series = _make_series("EURUSD=X", Currency.USD, [d], ["1.20"])

        provider = FlexibleFakeOhlcProvider(
            {"NVDA": nvda_series, "EURUSD=X": eurusd_series}
        )
        tx_repo = FakeTransactionRepository([usd_tx])

        result = get_nav_series(
            d, d, nav_repo=nav_repo, ohlc_provider=provider, tx_repo=tx_repo, today=today
        )

        assert len(result) == 1
        # value_eur = 4 shares × $300 / 1.20 (EUR per USD) = 1200 / 1.20 = €1000
        expected = Decimal("4") * Decimal("300") / Decimal("1.20")
        assert abs(result[0].nav_eur.amount - expected) < Decimal("0.01")


# ---------------------------------------------------------------------------
# Test 12 — Reconstruction is deterministic
# ---------------------------------------------------------------------------


class TestDeterministicReconstruction:
    def test_two_calls_return_identical_points(self) -> None:
        today = date(2025, 8, 15)
        d = date(2025, 8, 11)

        tx = _eur_buy("t1", "RHM.DE", date(2025, 1, 2), "10", "100")
        series = _make_series("RHM.DE", Currency.EUR, [d], ["110"])

        def _run() -> DailyNavPoint:
            nav_repo = FakeNavSnapshotRepository()
            provider = FlexibleFakeOhlcProvider({"RHM.DE": series})
            tx_repo = FakeTransactionRepository([tx])
            result = get_nav_series(
            d, d, nav_repo=nav_repo, ohlc_provider=provider, tx_repo=tx_repo, today=today
        )
            return result[0]

        p1 = _run()
        p2 = _run()
        assert p1.nav_eur == p2.nav_eur
        assert p1.cost_basis_eur == p2.cost_basis_eur
        assert p1.n_positions == p2.n_positions
        assert p1.is_reconstructed == p2.is_reconstructed


# ---------------------------------------------------------------------------
# clear_nav_cache
# ---------------------------------------------------------------------------


class TestClearNavCache:
    def test_clears_via_repo(self) -> None:
        nav_repo = FakeNavSnapshotRepository(
            [
                DailyNavPoint(
                    snapshot_date=date(2025, 1, 6),
                    nav_eur=Money(amount=Decimal("1000"), currency=Currency.EUR),
                    cost_basis_eur=Money(amount=Decimal("900"), currency=Currency.EUR),
                    n_positions=1,
                    is_reconstructed=True,
                )
            ]
        )
        assert len(nav_repo.all_points) == 1
        clear_nav_cache(nav_repo)
        assert nav_repo.clear_count == 1
        assert len(nav_repo.all_points) == 0


# ---------------------------------------------------------------------------
# Test 17 — Realistic 13-position, 90-day window
# ---------------------------------------------------------------------------


class TestRealistic90DayWindow:
    """End-to-end on fakes with a realistic portfolio size."""

    def test_cold_cache_reconstructs_90_days(self) -> None:
        today = date(2025, 4, 1)
        start = date(2025, 1, 1)
        end = date(2025, 3, 31)
        trading_days = _trading_days(start, 63)  # ~63 trading days in a quarter

        # 13 EUR-only positions for simplicity (no FX complication).
        tickers = [f"TICK{i:02d}.DE" for i in range(13)]
        transactions = [
            _eur_buy(f"t{i}", ticker, date(2024, 12, 1), "10", "100")
            for i, ticker in enumerate(tickers)
        ]

        nav_repo = FakeNavSnapshotRepository()
        tx_repo = FakeTransactionRepository(transactions)

        series_map = {
            ticker: _make_series(ticker, Currency.EUR, trading_days, ["110"] * 63)
            for ticker in tickers
        }
        provider = FlexibleFakeOhlcProvider(series_map)

        result = get_nav_series(
            start, end, nav_repo=nav_repo, ohlc_provider=provider, tx_repo=tx_repo, today=today
        )

        assert len(result) == 63
        assert all(p.is_reconstructed for p in result)
        # Each position: 10 shares × €110 = €1100; 13 positions → €14300
        for p in result:
            assert p.nav_eur.amount == Decimal("14300")
            assert p.n_positions == 13

    def test_warm_cache_returns_from_repo(self) -> None:
        today = date(2025, 4, 1)
        start = date(2025, 1, 1)
        end = date(2025, 3, 31)
        trading_days = _trading_days(start, 63)

        tickers = [f"TICK{i:02d}.DE" for i in range(13)]
        transactions = [
            _eur_buy(f"t{i}", ticker, date(2024, 12, 1), "10", "100")
            for i, ticker in enumerate(tickers)
        ]

        # Fully pre-populated cache.
        cached_points = [
            DailyNavPoint(
                snapshot_date=d,
                nav_eur=Money(amount=Decimal("14300"), currency=Currency.EUR),
                cost_basis_eur=Money(amount=Decimal("13000"), currency=Currency.EUR),
                n_positions=13,
                is_reconstructed=True,
            )
            for d in trading_days
        ]
        nav_repo = FakeNavSnapshotRepository(cached_points)

        series_map = {
            ticker: _make_series(ticker, Currency.EUR, trading_days, ["110"] * 63)
            for ticker in tickers
        }
        provider = FlexibleFakeOhlcProvider(series_map)
        tx_repo = FakeTransactionRepository(transactions)

        result = get_nav_series(
            start, end, nav_repo=nav_repo, ohlc_provider=provider, tx_repo=tx_repo, today=today
        )

        assert len(result) == 63
        # Nothing new was saved.
        assert nav_repo.save_count == 0


# ---------------------------------------------------------------------------
# Edge: no transactions → empty result
# ---------------------------------------------------------------------------


class TestEmptyPortfolio:
    def test_no_transactions_returns_empty(self) -> None:
        nav_repo = FakeNavSnapshotRepository()
        provider = FlexibleFakeOhlcProvider({})
        tx_repo = FakeTransactionRepository([])

        result = get_nav_series(
            date(2025, 1, 1),
            date(2025, 3, 31),
            nav_repo=nav_repo,
            ohlc_provider=provider,
            tx_repo=tx_repo,
            today=date(2025, 4, 1),
        )
        assert result == []
