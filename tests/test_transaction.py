"""
tests/test_transaction.py

Tests for Transaction model, replay_transactions(), and Position derived state.
All expected values calculated independently before writing assertions.
"""

import pytest
from datetime import date

from pydantic import ValidationError

from app.core.lot import OpenLot, RealisedDisposal, replay_transactions
from app.core.transaction import Transaction
from app.core.position import Position


# ── helpers ───────────────────────────────────────────────────────────────────

def _buy(ticker: str, trade_date: date, shares: float, price: float, id: str | None = None) -> Transaction:
    kwargs = dict(ticker=ticker, trade_date=trade_date, trade_type="buy", shares=shares, price=price)
    if id:
        kwargs["id"] = id
    return Transaction(**kwargs)


def _sell(ticker: str, trade_date: date, shares: float, price: float, id: str | None = None) -> Transaction:
    kwargs = dict(ticker=ticker, trade_date=trade_date, trade_type="sell", shares=shares, price=price)
    if id:
        kwargs["id"] = id
    return Transaction(**kwargs)


# ── replay_transactions ───────────────────────────────────────────────────────

class TestReplayTransactions:
    def test_replay_buys_only(self):
        txns = [
            _buy("NVDA", date(2025, 1, 1), shares=5.0, price=100.0),
            _buy("NVDA", date(2025, 2, 1), shares=3.0, price=110.0),
            _buy("NVDA", date(2025, 3, 1), shares=2.0, price=120.0),
        ]
        open_lots, realised = replay_transactions(txns)

        assert len(open_lots) == 3
        assert realised == []
        assert sum(l.shares for l in open_lots) == pytest.approx(10.0)

    def test_replay_one_full_sell(self):
        txns = [
            _buy("NVDA", date(2025, 1, 1), shares=10.0, price=100.0),
            _sell("NVDA", date(2025, 6, 1), shares=10.0, price=130.0),
        ]
        open_lots, realised = replay_transactions(txns)

        assert open_lots == []
        assert len(realised) == 1
        assert realised[0].total_gain == pytest.approx(10.0 * (130.0 - 100.0))  # 300

    def test_replay_partial_sell_keeps_remainder(self):
        txns = [
            _buy("NVDA", date(2025, 1, 1), shares=10.0, price=100.0),
            _sell("NVDA", date(2025, 6, 1), shares=4.0, price=130.0),
        ]
        open_lots, realised = replay_transactions(txns)

        assert len(open_lots) == 1
        assert open_lots[0].shares == pytest.approx(6.0)
        assert len(realised) == 1
        assert realised[0].total_gain == pytest.approx(4.0 * (130.0 - 100.0))  # 120

    def test_replay_sell_across_two_lots_fifo_order(self):
        # Buy 5 @ 100, buy 5 @ 120; sell 7 — should consume all of lot 1 and 2 from lot 2
        txns = [
            _buy("NVDA", date(2025, 1, 1), shares=5.0, price=100.0),
            _buy("NVDA", date(2025, 3, 1), shares=5.0, price=120.0),
            _sell("NVDA", date(2025, 6, 1), shares=7.0, price=150.0),
        ]
        open_lots, realised = replay_transactions(txns)

        assert len(open_lots) == 1
        assert open_lots[0].shares == pytest.approx(3.0)
        assert open_lots[0].purchase_price == pytest.approx(120.0)  # FIFO: lot 2 partially remains

        assert len(realised) == 1
        d = realised[0]
        assert len(d.disposals) == 2
        # First disposal: lot 1 (5 shares @ 100)
        assert d.disposals[0].purchase_price == pytest.approx(100.0)
        assert d.disposals[0].shares_disposed == pytest.approx(5.0)
        # Second disposal: 2 shares from lot 2 @ 120
        assert d.disposals[1].purchase_price == pytest.approx(120.0)
        assert d.disposals[1].shares_disposed == pytest.approx(2.0)
        # total_gain: 5*(150-100) + 2*(150-120) = 250 + 60 = 310
        assert d.total_gain == pytest.approx(310.0)

    def test_replay_oversell_raises(self):
        txns = [
            _buy("NVDA", date(2025, 1, 1), shares=5.0, price=100.0),
            _sell("NVDA", date(2025, 6, 1), shares=10.0, price=130.0),
        ]
        with pytest.raises(ValueError, match="only"):
            replay_transactions(txns)

    def test_replay_unsorted_input_sorted_by_date(self):
        # Provide sell before buy in list, but sell date is after buy date
        txns = [
            _sell("NVDA", date(2025, 6, 1), shares=5.0, price=130.0),
            _buy("NVDA", date(2025, 1, 1), shares=5.0, price=100.0),
        ]
        # Should sort by date — buy first, then sell — no error
        open_lots, realised = replay_transactions(txns)

        assert open_lots == []
        assert len(realised) == 1
        assert realised[0].total_gain == pytest.approx(5.0 * (130.0 - 100.0))


# ── Position with transaction log ─────────────────────────────────────────────

class TestPositionTransactionLog:
    def test_position_total_shares_after_sell(self):
        pos = Position(
            ticker="NVDA",
            name="Nvidia",
            transactions=[
                _buy("NVDA", date(2025, 1, 1), shares=10.0, price=100.0),
                _sell("NVDA", date(2025, 6, 1), shares=4.0, price=130.0),
            ],
        )
        assert pos.total_shares == pytest.approx(6.0)

    def test_position_realised_gain_after_sell(self):
        # Buy 10 @ 100, sell 5 @ 150 → gain = 5 * 50 = 250
        pos = Position(
            ticker="NVDA",
            name="Nvidia",
            transactions=[
                _buy("NVDA", date(2025, 1, 1), shares=10.0, price=100.0),
                _sell("NVDA", date(2025, 6, 1), shares=5.0, price=150.0),
            ],
        )
        total_gain = sum(d.total_gain for d in pos.realised_disposals)
        assert total_gain == pytest.approx(250.0)
        assert pos.total_shares == pytest.approx(5.0)

    def test_position_empty_transactions_is_valid(self):
        pos = Position(ticker="NVDA", name="Nvidia")
        assert pos.total_shares == pytest.approx(0.0)
        assert pos.average_cost is None
        assert pos.open_lots == []
        assert pos.realised_disposals == []
