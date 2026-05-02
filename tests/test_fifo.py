"""
tests/test_fifo.py

FIFO disposal engine tests using a realistic SK Hynix lot sequence.
All expected values calculated independently before writing assertions.
"""

import pytest
from datetime import date

from pydantic import ValidationError

from app.core.lot import OpenLot, FifoResult, dispose_fifo


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def hy9h_lots() -> list[OpenLot]:
    """Three SK Hynix GDR lots in chronological order."""
    return [
        OpenLot(ticker="HY9H.F", purchase_date=date(2024, 11, 15), purchase_price=28.50, shares=10.0),
        OpenLot(ticker="HY9H.F", purchase_date=date(2025,  3, 20), purchase_price=31.20, shares=6.0),
        OpenLot(ticker="HY9H.F", purchase_date=date(2025,  9,  5), purchase_price=26.80, shares=8.0),
    ]


# ── OpenLot model ─────────────────────────────────────────────────────────────

class TestOpenLotModel:
    def test_cost_basis(self):
        lot = OpenLot(ticker="HY9H.F", purchase_date=date(2025, 1, 1), purchase_price=30.0, shares=6.0)
        assert lot.cost_basis == pytest.approx(180.0)

    def test_ticker_normalised_to_uppercase(self):
        lot = OpenLot(ticker=" nvda ", purchase_date=date(2025, 1, 1), purchase_price=100.0, shares=5.0)
        assert lot.ticker == "NVDA"

    def test_id_auto_generated(self):
        lot = OpenLot(ticker="NVDA", purchase_date=date(2025, 1, 1), purchase_price=100.0, shares=5.0)
        assert lot.id and len(lot.id) > 0

    def test_id_preserved_when_supplied(self):
        lot = OpenLot(id="my-lot-1", ticker="NVDA", purchase_date=date(2025, 1, 1), purchase_price=100.0, shares=5.0)
        assert lot.id == "my-lot-1"

    def test_rejects_negative_price(self):
        with pytest.raises(ValidationError):
            OpenLot(ticker="NVDA", purchase_date=date(2025, 1, 1), purchase_price=-1.0, shares=5.0)

    def test_rejects_zero_shares(self):
        with pytest.raises(ValidationError):
            OpenLot(ticker="NVDA", purchase_date=date(2025, 1, 1), purchase_price=100.0, shares=0.0)

    def test_fractional_shares_allowed(self):
        lot = OpenLot(ticker="NVDA", purchase_date=date(2025, 1, 1), purchase_price=100.0, shares=0.5)
        assert lot.shares == 0.5
        assert lot.cost_basis == pytest.approx(50.0)


# ── FIFO disposal: consume entire lots ───────────────────────────────────────

class TestFifoFullLotConsumption:
    def test_sell_entire_first_lot(self, hy9h_lots):
        # Sell 10 shares at 35.00 — exactly lot 1
        result = dispose_fifo(hy9h_lots, shares_to_sell=10.0, sell_price=35.00)

        assert len(result.disposals) == 1
        d = result.disposals[0]
        assert d.purchase_date == date(2024, 11, 15)
        assert d.shares_disposed == pytest.approx(10.0)
        assert d.cost_basis == pytest.approx(285.0)       # 28.50 × 10
        assert d.proceeds == pytest.approx(350.0)         # 35.00 × 10
        assert d.gain == pytest.approx(65.0)

        assert len(result.remaining_lots) == 2
        assert result.remaining_lots[0].purchase_date == date(2025, 3, 20)
        assert result.remaining_lots[1].purchase_date == date(2025, 9, 5)

    def test_sell_first_two_lots(self, hy9h_lots):
        # Sell 16 shares at 35.00 — lots 1 (10) + 2 (6)
        result = dispose_fifo(hy9h_lots, shares_to_sell=16.0, sell_price=35.00)

        assert len(result.disposals) == 2
        assert result.total_proceeds == pytest.approx(560.0)  # 16 × 35
        assert result.total_cost_basis == pytest.approx(472.2)  # 285 + 187.20
        assert result.total_gain == pytest.approx(87.8)

        assert len(result.remaining_lots) == 1
        assert result.remaining_lots[0].purchase_date == date(2025, 9, 5)
        assert result.remaining_lots[0].shares == pytest.approx(8.0)

    def test_sell_all_lots(self, hy9h_lots):
        result = dispose_fifo(hy9h_lots, shares_to_sell=24.0, sell_price=35.00)

        assert len(result.disposals) == 3
        assert len(result.remaining_lots) == 0
        assert result.total_proceeds == pytest.approx(840.0)
        assert result.total_cost_basis == pytest.approx(686.6)
        assert result.total_gain == pytest.approx(153.4)


# ── FIFO disposal: partial lot consumption ────────────────────────────────────

class TestFifoPartialLotConsumption:
    def test_sell_partial_first_lot(self, hy9h_lots):
        # Sell 4 shares from lot 1 (10 shares)
        result = dispose_fifo(hy9h_lots, shares_to_sell=4.0, sell_price=35.00)

        assert len(result.disposals) == 1
        d = result.disposals[0]
        assert d.shares_disposed == pytest.approx(4.0)
        assert d.gain == pytest.approx(4.0 * (35.00 - 28.50))  # 26.00

        # Lot 1 remains with 6 shares, lots 2 and 3 untouched
        assert len(result.remaining_lots) == 3
        first_remaining = result.remaining_lots[0]
        assert first_remaining.purchase_date == date(2024, 11, 15)
        assert first_remaining.shares == pytest.approx(6.0)
        assert first_remaining.purchase_price == pytest.approx(28.50)
        # Lot id preserved on partial remainder
        assert first_remaining.id == d.lot_id

    def test_sell_crosses_two_lots_with_partial(self, hy9h_lots):
        # Sell 12 shares: all 10 of lot 1 + 2 from lot 2
        result = dispose_fifo(hy9h_lots, shares_to_sell=12.0, sell_price=35.00)

        assert len(result.disposals) == 2
        assert result.disposals[0].shares_disposed == pytest.approx(10.0)
        assert result.disposals[1].shares_disposed == pytest.approx(2.0)
        assert result.disposals[1].gain == pytest.approx(2.0 * (35.00 - 31.20))  # 7.60
        assert result.total_gain == pytest.approx(72.6)   # 65 + 7.6

        # Lot 2 has 4 remaining, lot 3 untouched
        assert len(result.remaining_lots) == 2
        assert result.remaining_lots[0].shares == pytest.approx(4.0)
        assert result.remaining_lots[1].shares == pytest.approx(8.0)


# ── FIFO disposal: loss realisation ──────────────────────────────────────────

class TestFifoLossRealisation:
    def test_sell_at_loss(self):
        lot = OpenLot(ticker="MU", purchase_date=date(2025, 4, 1), purchase_price=95.0, shares=6.0)
        result = dispose_fifo([lot], shares_to_sell=6.0, sell_price=80.0)

        assert result.total_gain == pytest.approx(6.0 * (80.0 - 95.0))  # -90.0
        assert result.is_loss
        assert not result.is_gain


# ── FIFO ordering: lots supplied out of order ─────────────────────────────────

class TestFifoOrdering:
    def test_fifo_order_enforced_regardless_of_input_order(self):
        """Lots supplied newest-first must still be disposed oldest-first."""
        lots_reversed = [
            OpenLot(ticker="NVDA", purchase_date=date(2025, 6, 1), purchase_price=130.0, shares=3.0),
            OpenLot(ticker="NVDA", purchase_date=date(2025, 1, 1), purchase_price=110.0, shares=3.0),
        ]
        result = dispose_fifo(lots_reversed, shares_to_sell=3.0, sell_price=150.0)

        # Should consume the Jan lot (oldest), not the Jun lot
        assert result.disposals[0].purchase_date == date(2025, 1, 1)
        assert result.disposals[0].purchase_price == pytest.approx(110.0)


# ── FIFO disposal: fractional shares ─────────────────────────────────────────

class TestFifoFractionalShares:
    def test_fractional_disposal(self):
        lot = OpenLot(ticker="NVDA", purchase_date=date(2025, 1, 1), purchase_price=100.0, shares=10.0)
        result = dispose_fifo([lot], shares_to_sell=0.5, sell_price=120.0)

        assert result.disposals[0].shares_disposed == pytest.approx(0.5)
        assert result.disposals[0].gain == pytest.approx(10.0)  # 0.5 × (120 - 100)
        assert result.remaining_lots[0].shares == pytest.approx(9.5)


# ── FIFO disposal: guard conditions ──────────────────────────────────────────

class TestFifoGuards:
    def test_oversell_raises(self, hy9h_lots):
        with pytest.raises(ValueError, match="only"):
            dispose_fifo(hy9h_lots, shares_to_sell=25.0, sell_price=35.00)

    def test_zero_shares_raises(self, hy9h_lots):
        with pytest.raises(ValueError, match="positive"):
            dispose_fifo(hy9h_lots, shares_to_sell=0.0, sell_price=35.00)

    def test_negative_shares_raises(self, hy9h_lots):
        with pytest.raises(ValueError, match="positive"):
            dispose_fifo(hy9h_lots, shares_to_sell=-1.0, sell_price=35.00)

    def test_zero_sell_price_raises(self, hy9h_lots):
        with pytest.raises(ValueError, match="positive"):
            dispose_fifo(hy9h_lots, shares_to_sell=1.0, sell_price=0.0)

    def test_negative_sell_price_raises(self, hy9h_lots):
        with pytest.raises(ValueError, match="positive"):
            dispose_fifo(hy9h_lots, shares_to_sell=1.0, sell_price=-10.0)


# ── FifoResult properties ─────────────────────────────────────────────────────

class TestFifoResultProperties:
    def test_is_gain(self, hy9h_lots):
        result = dispose_fifo(hy9h_lots, shares_to_sell=10.0, sell_price=35.00)
        assert result.is_gain
        assert not result.is_loss

    def test_is_loss(self):
        lot = OpenLot(ticker="HY9H.F", purchase_date=date(2025, 1, 1), purchase_price=35.0, shares=5.0)
        result = dispose_fifo([lot], shares_to_sell=5.0, sell_price=30.0)
        assert result.is_loss
        assert not result.is_gain
